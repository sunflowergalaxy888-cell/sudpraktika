# scripts/telegram_injector.py
# Інджестер для автоматичного додавання рішень ВС з Telegram каналу

import requests
import re
import os
import json
import yaml
from datetime import datetime, timezone
import logging
from typing import List, Dict, Optional

# Налаштування логування
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TelegramInjector:
    def __init__(self):
        self.bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
        self.channel_username = os.environ.get('TELEGRAM_CHANNEL', '@supremecourt_ukraine')  # Приклад
        self.processed_file = '_data/processed_posts.json'
        self.decisions_dir = '_decisions'
        
        # Створюємо необхідні директорії
        os.makedirs(self.decisions_dir, exist_ok=True)
        os.makedirs('_data', exist_ok=True)
        
        # Ініціалізуємо словники для розпізнавання статей КК
        self.init_article_keywords()
    
    def init_article_keywords(self):
        """Ініціалізує словник ключових слів для розпізнавання статей КК"""
        
        # Базовий словник найпоширеніших статей
        self.article_keywords = {
            # Злочини проти власності
            185: ['крадіжка', 'таємно', 'чужого майна', 'привласнення'],
            186: ['грабіж', 'відкрито', 'заволодіння'],
            187: ['розбій', 'напад', 'озброєний', 'погроза застосування'],
            189: ['вимагання', 'погроза розголошення', 'шантаж'],
            190: ['шахрайство', 'обман', 'зловживання довірою'],
            
            # Злочини проти життя та здоров'я
            115: ['вбивство', 'умисне позбавлення життя', 'позбавлення життя'],
            116: ['перевищення меж необхідної оборони', 'необхідна оборона'],
            118: ['вбивство у стані сильного душевного хвилювання'],
            119: ['вбивство через необережність', 'необережність'],
            120: ['доведення до самогубства'],
            121: ['умисне тяжке тілесне ушкодження', 'тяжке тілесне'],
            122: ['умисне середньої тяжкості тілесне ушкодження'],
            125: ['умисне легке тілесне ушкодження'],
            126: ['побої і мордування'],
            127: ['катування'],
            
            # Злочини у сфері обігу наркотичних засобів
            307: ['наркотичні засоби', 'психотропні речовини', 'наркотики'],
            309: ['незаконне виробництво наркотичних засобів'],
            
            # Злочини проти безпеки дорожнього руху
            286: ['порушення правил безпеки дорожнього руху', 'ДТП'],
            
            # Злочини проти статевої свободи та недоторканності
            152: ['згвалтування'],
            153: ['примушування до вступу в статевий зв\'язок'],
            
            # Службові злочини
            364: ['зловживання владою або службовим становищем'],
            365: ['перевищення влади або службових повноважень'],
            366: ['службове підроблення'],
            368: ['прийняття пропозиції, обіцянки або одержання неправомірної вигоди службовою особою'],
            369: ['незаконне збагачення'],
            
            # Злочини проти правосуддя
            382: ['невиконання судового рішення'],
            384: ['примушування давати показання'],
            387: ['розголошення даних оперативно-розшукової діяльності'],
            
            # Військові злочини
            408: ['самовільне залишення військової частини або місця служби'],
            409: ['дезертирство'],
            425: ['непокора']
        }
        
        # Додаємо регулярні вирази для пошуку статей
        self.article_patterns = [
            r'ст(?:аття)?\s*\.?\s*(\d+)(?:\s*(?:частина|ч)\s*\.?\s*(\d+))?',  # ст. 185, стаття 185 ч. 2
            r'(\d+)\s*(?:частина|ч)\s*\.?\s*(\d+)\s*КК',  # 185 частина 2 КК
            r'КК\s*(?:України)?\s*(\d+)',  # КК України 185
            r'Кримінальний\s*кодекс.*?(\d+)'  # Кримінальний кодекс... 185
        ]
    
    def get_channel_posts(self, limit: int = 100) -> List[Dict]:
        """
        Отримує останні пости з Telegram каналу
        
        Args:
            limit: Максимальна кількість постів для отримання
            
        Returns:
            Список словників з інформацією про пости
        """
        posts = []
        
        try:
            # Використовуємо Telegram Bot API для отримання постів
            url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates"
            params = {
                'limit': limit,
                'offset': -limit  # Отримуємо останні пости
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            if not data.get('ok'):
                logger.error(f"Telegram API помилка: {data.get('description')}")
                return posts
            
            # Обробляємо отримані повідомлення
            for update in data.get('result', []):
                if 'channel_post' in update:
                    post = update['channel_post']
                    
                    # Перевіряємо, що це пост з потрібного каналу
                    if post.get('chat', {}).get('username') == self.channel_username.replace('@', ''):
                        if 'text' in post and post['text'].strip():
                            posts.append({
                                'id': post['message_id'],
                                'text': post['text'],
                                'date': post['date'],
                                'chat_id': post['chat']['id']
                            })
            
            logger.info(f"Отримано {len(posts)} постів з каналу {self.channel_username}")
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Помилка запиту до Telegram API: {e}")
        except Exception as e:
            logger.error(f"Неочікувана помилка: {e}")
        
        return posts
    
    def detect_articles(self, text: str) -> List[int]:
        """
        Визначає номери статей КК за текстом рішення
        
        Args:
            text: Текст для аналізу
            
        Returns:
            Список номерів статей КК
        """
        detected_articles = set()
        text_lower = text.lower()
        
        # 1. Прямий пошук номерів статей за регулярними виразами
        for pattern in self.article_patterns:
            matches = re.finditer(pattern, text_lower, re.IGNORECASE)
            for match in matches:
                try:
                    article_num = int(match.group(1))
                    # Перевіряємо, що номер статті в межах КК України
                    if 1 <= article_num <= 447:
                        detected_articles.add(article_num)
                        logger.debug(f"Знайдена стаття {article_num} за патерном: {match.group(0)}")
                except (ValueError, IndexError):
                    continue
        
        # 2. Пошук за ключовими словами
        for article_num, keywords in self.article_keywords.items():
            for keyword in keywords:
                if keyword.lower() in text_lower:
                    detected_articles.add(article_num)
                    logger.debug(f"Знайдена стаття {article_num} за ключовим словом: {keyword}")
                    break  # Достатньо одного збігу для статті
        
        # 3. Контекстний аналіз для складних випадків
        detected_articles.update(self._contextual_analysis(text_lower))
        
        result = sorted(list(detected_articles))
        logger.info(f"Виявлено статті КК: {result}")
        
        return result
    
    def _contextual_analysis(self, text: str) -> List[int]:
        """Додатковий контекстний аналіз для складних випадків"""
        articles = []
        
        # Аналіз контексту для кримінальних справ
        contexts = {
            'власність': [185, 186, 187, 189, 190],  # Злочини проти власності
            'життя': [115, 116, 118, 119],  # Злочини проти життя
            'здоров\'я': [121, 122, 125, 126, 127],  # Злочини проти здоров'я
            'наркотики': [307, 309],  # Наркозлочини
            'дорожній рух': [286],  # ДТП
            'службов': [364, 365, 366, 368, 369],  # Службові злочини
            'хабар': [368, 369],  # Корупційні злочини
        }
        
        for context_key, context_articles in contexts.items():
            if context_key in text:
                # Додаємо найбільш вірогідну статтю з контексту
                articles.extend(context_articles[:2])  # Обмежуємо кількість
        
        return articles[:5]  # Обмежуємо загальну кількість
    
    def load_processed_posts(self) -> List[int]:
        """Завантажує список ID оброблених постів"""
        if os.path.exists(self.processed_file):
            try:
                with open(self.processed_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get('processed_posts', [])
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Помилка читання файлу processed_posts.json: {e}")
        
        return []
    
    def save_processed_posts(self, processed_posts: List[int]):
        """Зберігає список ID оброблених постів"""
        try:
            data = {
                'processed_posts': processed_posts,
                'last_update': datetime.now().isoformat(),
                'total_processed': len(processed_posts)
            }
            
            with open(self.processed_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                
            logger.info(f"Збережено {len(processed_posts)} оброблених постів")
            
        except Exception as e:
            logger.error(f"Помилка збереження processed_posts.json: {e}")
    
    def create_slug(self, title: str) -> str:
        """Створює URL-slug з заголовка"""
        # Транслітерація українських літер
        translit_dict = {
            'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'ґ': 'g', 'д': 'd', 'е': 'e',
            'є': 'ye', 'ж': 'zh', 'з': 'z', 'и': 'y', 'і': 'i', 'ї': 'yi', 'й': 'y',
            'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r',
            'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'h', 'ц': 'c', 'ч': 'ch',
            'ш': 'sh', 'щ': 'sch', 'ь': '', 'ю': 'yu', 'я': 'ya'
        }
        
        slug = title.lower().strip()
        
        # Транслітерація
        for uk_char, en_char in translit_dict.items():
            slug = slug.replace(uk_char, en_char)
        
        # Залишаємо тільки букви, цифри, пробіли та дефіси
        slug = re.sub(r'[^a-z0-9\s\-]', '', slug)
        
        # Замінюємо пробіли на дефіси
        slug = re.sub(r'\s+', '-', slug)
        
        # Прибираємо множинні дефіси
        slug = re.sub(r'-+', '-', slug)
        
        # Прибираємо дефіси на початку та в кінці
        slug = slug.strip('-')
        
        # Обмежуємо довжину
        return slug[:50]
    
    def create_decision_file(self, post: Dict, article_numbers: List[int]) -> Optional[str]:
        """
        Створює файл рішення ВС у форматі Jekyll
        
        Args:
            post: Дані про пост з Telegram
            article_numbers: Список номерів статей КК
            
        Returns:
            Шлях до створеного файлу або None при помилці
        """
        try:
            # Генеруємо дату з timestamp
            post_date = datetime.fromtimestamp(post['date'], tz=timezone.utc)
            date_str = post_date.strftime('%Y-%m-%d')
            
            # Генеруємо заголовок (перші 80 символів тексту)
            title = re.sub(r'\s+', ' ', post['text'][:80].strip())
            if len(post['text']) > 80:
                title += '...'
            
            # Створюємо slug для файла
            title_slug = self.create_slug(title)
            if not title_slug:
                title_slug = f"post-{post['id']}"
            
            # Генеруємо ім'я файлу
            filename = f"{self.decisions_dir}/{date_str}-{title_slug}.md"
            
            # Якщо файл вже існує, додаємо ID поста
            if os.path.exists(filename):
                filename = f"{self.decisions_dir}/{date_str}-{title_slug}-{post['id']}.md"
            
            # Готуємо YAML Front Matter
            front_matter = {
                'title': title,
                'date': date_str,
                'post_id': post['id'],
                'article_numbers': article_numbers,
                'layout': 'decision',
                'source': 'Telegram канал Верховного Суду',
                'auto_generated': True
            }
            
            # Очищуємо та форматуємо текст
            content = post['text'].strip()
            content = re.sub(r'\n\s*\n', '\n\n', content)  # Нормалізуємо абзаци
            
            # Створюємо вміст файлу
            file_content = f"""---
{yaml.dump(front_matter, allow_unicode=True, default_flow_style=False)}---

{content}

---

**Джерело:** Офіційний канал Верховного Суду України  
**Дата публікації:** {post_date.strftime('%d.%m.%Y %H:%M')}  
**ID поста:** {post['id']}

{% if page.article_numbers %}
**Статті КК:** {% for article_num in page.article_numbers %}[{{ article_num }}](/stattya-{{ article_num }}/){% unless forloop.last %}, {% endunless %}{% endfor %}
{% endif %}
"""
            
            # Записуємо файл
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(file_content)
            
            logger.info(f"Створено файл рішення: {filename}")
            return filename
            
        except Exception as e:
            logger.error(f"Помилка створення файлу рішення: {e}")
            return None
    
    def run(self):
        """Головна функція інджестера"""
        logger.info("🚀 Запуск інджестера SudPraktika")
        logger.info("=" * 50)
        
        # Перевіряємо наявність токена
        if not self.bot_token:
            logger.error("❌ TELEGRAM_BOT_TOKEN не налаштований")
            return False
        
        # Завантажуємо список оброблених постів
        processed_posts = self.load_processed_posts()
        logger.info(f"📋 Знайдено {len(processed_posts)} оброблених постів")
        
        # Отримуємо нові пости з Telegram
        logger.info(f"📡 Отримання постів з каналу {self.channel_username}...")
        posts = self.get_channel_posts()
        
        if not posts:
            logger.warning("⚠️ Не отримано жодного поста")
            return False
        
        # Обробляємо нові пости
        new_decisions = 0
        new_processed = processed_posts.copy()
        
        for post in posts:
            post_id = post['id']
            
            if post_id not in processed_posts:
                logger.info(f"🔍 Обробка поста {post_id}...")
                
                # Визначаємо статті КК
                article_numbers = self.detect_articles(post['text'])
                
                if article_numbers:
                    # Створюємо файл рішення
                    decision_file = self.create_decision_file(post, article_numbers)
                    
                    if decision_file:
                        new_decisions += 1
                        logger.info(f"✅ Створено рішення для статей {article_numbers}")
                    else:
                        logger.warning(f"⚠️ Не вдалося створити файл для поста {post_id}")
                else:
                    logger.info(f"ℹ️ Пост {post_id} не містить посилань на статті КК")
                
                # Додаємо до оброблених
                new_processed.append(post_id)
            else:
                logger.debug(f"⏭️ Пост {post_id} вже оброблено")
        
        # Зберігаємо оновлений список оброблених постів
        self.save_processed_posts(new_processed)
        
        # Виводимо підсумок
        logger.info("=" * 50)
        logger.info(f"✅ Обробку завершено успішно!")
        logger.info(f"📊 Статистика:")
        logger.info(f"   • Постів отримано: {len(posts)}")
        logger.info(f"   • Нових рішень створено: {new_decisions}")
        logger.info(f"   • Всього оброблено постів: {len(new_processed)}")
        
        return True

def main():
    """Точка входу для запуску інджестера"""
    injector = TelegramInjector()
    success = injector.run()
    
    if success:
        print("🎉 Інджестер завершив роботу успішно!")
        return 0
    else:
        print("❌ Під час роботи інджестера виникли помилки")
        return 1

if __name__ == "__main__":
    import sys
    sys.exit(main())
