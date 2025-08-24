# scripts/parse_criminal_code.py
# Парсер PDF Кримінального кодексу України для SudPraktika

import PyPDF2
import re
import os
import yaml
from datetime import datetime

class CriminalCodeParser:
    def __init__(self, pdf_path):
        self.pdf_path = pdf_path
        self.articles = []
        self.sections = []
        
    def extract_text_from_pdf(self):
        """Витягує текст з PDF файлу"""
        try:
            with open(self.pdf_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                text = ""
                
                print(f"Обробка PDF: {len(reader.pages)} сторінок")
                
                for i, page in enumerate(reader.pages):
                    page_text = page.extract_text()
                    text += page_text + "\n"
                    
                    if i % 50 == 0:
                        print(f"Оброблено {i} сторінок...")
                
                return text
                
        except Exception as e:
            print(f"Помилка читання PDF: {e}")
            return None
    
    def parse_structure(self, text):
        """Парсить структуру КК"""
        
        # Очищуємо текст від зайвих символів
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'[\u00A0\u2000-\u200B\u2028\u2029]', ' ', text)
        
        # Шукаємо розділи
        section_pattern = r'РОЗДІЛ\s+([IVX]+)\.?\s*([А-ЯІЇЄҐ][^А-Я]*?)(?=РОЗДІЛ|$)'
        sections = re.findall(section_pattern, text, re.DOTALL | re.IGNORECASE)
        
        print(f"Знайдено розділів: {len(sections)}")
        for i, (num, title) in enumerate(sections[:5]):  # Показуємо перші 5
            print(f"  {num}: {title[:50]}...")
        
        # Шукаємо статті - різні можливі формати
        article_patterns = [
            r'Стаття\s+(\d+)\.?\s*([А-ЯІЇЄҐ][^\.]*?)\.?\s*(.*?)(?=Стаття\s+\d+|$)',
            r'(\d+)\.?\s*([А-ЯІЇЄҐ][^\.]*?)\.?\s*(.*?)(?=\d+\.\s*[А-ЯІЇЄҐ]|$)',
        ]
        
        articles = []
        
        for pattern in article_patterns:
            matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)
            if matches:
                print(f"Знайдено {len(matches)} статей за патерном")
                articles.extend(matches)
                break
        
        # Обробляємо знайдені статті
        processed_articles = []
        for match in articles:
            if len(match) >= 3:
                number, title, content = match[0], match[1], match[2]
                
                try:
                    article_num = int(number)
                    
                    # Очищуємо назву статті
                    title = re.sub(r'^\W+|\W+$', '', title)
                    title = re.sub(r'\s+', ' ', title)
                    
                    # Очищуємо контент
                    content = re.sub(r'\s+', ' ', content).strip()
                    
                    # Обмежуємо довжину контенту для попереднього перегляду
                    if len(content) > 2000:
                        content = content[:2000] + "..."
                    
                    processed_articles.append({
                        'number': article_num,
                        'title': title,
                        'content': content,
                        'slug': self.create_slug(title)
                    })
                    
                except ValueError:
                    continue
        
        # Сортуємо за номером статті
        processed_articles.sort(key=lambda x: x['number'])
        
        print(f"Оброблено {len(processed_articles)} статей")
        if processed_articles:
            print("Перші 3 статті:")
            for article in processed_articles[:3]:
                print(f"  {article['number']}: {article['title']}")
        
        return processed_articles, sections
    
    def create_slug(self, title):
        """Створює slug для URL"""
        # Словник для транслітерації
        translit = {
            'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'ґ': 'g', 'д': 'd', 'е': 'e', 
            'є': 'ye', 'ж': 'zh', 'з': 'z', 'и': 'y', 'і': 'i', 'ї': 'yi', 'й': 'y',
            'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r',
            'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'h', 'ц': 'c', 'ч': 'ch',
            'ш': 'sh', 'щ': 'sch', 'ь': '', 'ю': 'yu', 'я': 'ya'
        }
        
        slug = title.lower()
        for ua, en in translit.items():
            slug = slug.replace(ua, en)
        
        # Залишаємо тільки букви, цифри та дефіси
        slug = re.sub(r'[^a-z0-9\s-]', '', slug)
        slug = re.sub(r'\s+', '-', slug)
        slug = re.sub(r'-+', '-', slug)
        
        return slug.strip('-')[:50]  # Обмежуємо довжину
    
    def create_jekyll_files(self, articles):
        """Створює файли для Jekyll"""
        
        # Створюємо директорії
        os.makedirs('_articles', exist_ok=True)
        os.makedirs('_data', exist_ok=True)
        
        # Створюємо файли статей
        created_files = []
        
        for article in articles:
            filename = f"_articles/{article['number']:03d}-{article['slug']}.md"
            
            # YAML Front Matter
            front_matter = {
                'title': f"Стаття {article['number']}. {article['title']}",
                'number': article['number'],
                'slug': article['slug'],
                'layout': 'article'
            }
            
            content = f"""---
{yaml.dump(front_matter, allow_unicode=True, default_flow_style=False)}---

# Стаття {article['number']}. {article['title']}

{article['content']}

## Практика Верховного Суду

<div class="decisions-container">
{{% for decision in site.decisions %}}
  {{% if decision.article_numbers contains {article['number']} %}}
    <div class="decision-item">
      <h4><a href="{{{{ decision.url }}}}">{{{{ decision.title }}}}</a></h4>
      <p class="decision-date">{{{{ decision.date | date: "%d.%m.%Y" }}}}</p>
      <p class="decision-excerpt">{{{{ decision.content | strip_html | truncate: 200 }}}}</p>
    </div>
  {{% endif %}}
{{% endfor %}}
</div>

<div class="article-navigation">
  {{% assign prev_article = site.articles | where: "number", {article['number'] - 1} | first %}}
  {{% assign next_article = site.articles | where: "number", {article['number'] + 1} | first %}}
  
  {{% if prev_article %}}
    <a href="{{{{ prev_article.url }}}}" class="prev-article">← Стаття {{{{ prev_article.number }}}}</a>
  {{% endif %}}
  
  {{% if next_article %}}
    <a href="{{{{ next_article.url }}}}" class="next-article">Стаття {{{{ next_article.number }}}} →</a>
  {{% endif %}}
</div>
"""
            
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(content)
                created_files.append(filename)
                
            except Exception as e:
                print(f"Помилка створення файлу {filename}: {e}")
        
        print(f"Створено {len(created_files)} файлів статей")
        
        # Створюємо індексний файл з усіма статтями
        self.create_index_data(articles)
        
        return created_files
    
    def create_index_data(self, articles):
        """Створює дані для головної сторінки"""
        
        # Групуємо статті за розділами (приблизно)
        sections_data = {
            'zagalna': {'title': 'Загальна частина', 'range': (1, 108), 'articles': []},
            'osoblyva': {'title': 'Особлива частина', 'range': (109, 447), 'articles': []}
        }
        
        for article in articles:
            if 1 <= article['number'] <= 108:
                sections_data['zagalna']['articles'].append(article)
            else:
                sections_data['osoblyva']['articles'].append(article)
        
        # Зберігаємо в YAML файл
        with open('_data/criminal_code.yml', 'w', encoding='utf-8') as f:
            yaml.dump(sections_data, f, allow_unicode=True, default_flow_style=False)
        
        print("Створено файл _data/criminal_code.yml")
    
    def run(self):
        """Запускає весь процес парсингу"""
        print("🚀 Запуск парсера Кримінального кодексу для SudPraktika")
        print("=" * 60)
        
        # Витягуємо текст
        print("📖 Читання PDF файлу...")
        text = self.extract_text_from_pdf()
        
        if not text:
            print("❌ Не вдалося прочитати PDF файл")
            return False
        
        print(f"✅ Витягнуто {len(text)} символів тексту")
        
        # Парсимо структуру
        print("\n🔍 Аналіз структури...")
        articles, sections = self.parse_structure(text)
        
        if not articles:
            print("❌ Не знайдено жодної статті")
            return False
        
        # Створюємо файли Jekyll
        print(f"\n📝 Створення {len(articles)} файлів...")
        created_files = self.create_jekyll_files(articles)
        
        print("\n✅ Парсинг завершено успішно!")
        print(f"📊 Статистика:")
        print(f"   • Статей оброблено: {len(articles)}")
        print(f"   • Файлів створено: {len(created_files)}")
        print(f"   • Діапазон статей: {min(a['number'] for a in articles)} - {max(a['number'] for a in articles)}")
        
        return True

# Використання
if __name__ == "__main__":
    # Вкажіть шлях до вашого PDF файлу
    pdf_path = "criminal_code.pdf"  # Замініть на реальний шлях
    
    if not os.path.exists(pdf_path):
        print(f"❌ Файл {pdf_path} не знайдено")
        print("Покладіть PDF файл Кримінального кодексу в папку scripts/ та вкажіть правильний шлях")
    else:
        parser = CriminalCodeParser(pdf_path)
        parser.run()
