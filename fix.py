import os
import base64
import re

# ПУТИ К ПАПКАМ
source_folder = os.path.expanduser("~/Desktop/CONVERT/OldSongs")
output_folder = os.path.expanduser("~/Desktop/CONVERT/NewSongs")

if not os.path.exists(output_folder):
    os.makedirs(output_folder)

def clean_rtf(text):
    # 1. Спецкоды кириллицы
    def decode_u(m):
        try: return chr(int(m.group(1)))
        except: return m.group(0)
    text = re.sub(r'\\u(\d{4})', decode_u, text)
    
    # 2. Убираем RTF мусор
    text = re.sub(r'\{\*?\\?[\s\S]+?\}', '', text)
    text = re.sub(r'\\[a-z0-9\-]+ ?', '', text)
    text = text.replace("'91", "'").replace("'92", "'").replace("'93", '"').replace("'94", '"')
    text = text.replace('\\', '').replace('}', '').replace('{', '')
    
    # 3. Склеиваем разорванные русские слова
    text = text.replace('  ', '|||')
    text = re.sub(r'(?<=[а-яА-ЯёЁ]) (?=[а-яА-ЯёЁ])', '', text)
    text = text.replace('|||', ' ')
    
    # 4. МАГИЯ: Если русский и английский слиплись, вставляем разделитель
    # Ищем место, где заканчивается русский и начинается английский (или наоборот)
    text = re.sub(r'([а-яА-ЯёЁ])\s*\n\s*([a-zA-Z])', r'\1\n-\n\2', text)
    text = re.sub(r'([a-zA-Z])\s*\n\s*([а-яА-ЯёЁ])', r'\1\n-\n\2', text)
    
    return text.strip()               


print("Начинаю финальную конвертацию...")

for filename in os.listdir(source_folder):
    if filename.endswith(".pro6"):
        try:
            with open(os.path.join(source_folder, filename), 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # Разбиваем на слайды
            slides = re.findall(r'<RVDisplaySlide.*?>.*?</RVDisplaySlide>', content, flags=re.DOTALL)
            all_song_slides = []
            
            for slide_xml in slides:
                # Ищем все текстовые поля внутри одного слайда (RU и EN)
                text_blocks = re.findall(r'<NSString rvXMLIvarName="RTFData">(.*?)</NSString>', slide_xml, flags=re.DOTALL)
                
                slide_parts = []
                for b64 in text_blocks:
                    try:
                        raw_bytes = base64.b64decode(b64)
                        # Сначала пробуем Windows-кодировку, затем UTF-8
                        try:
                            decoded = raw_bytes.decode('cp1251')
                        except:
                            decoded = raw_bytes.decode('utf-8', errors='ignore')
                        
                        cleaned = clean_rtf(decoded)
                        if cleaned:
                            slide_parts.append(cleaned)
                    except:
                        continue
                
                # Соединяем RU и EN внутри слайда через пустую строку с невидимым пробелом
                # Это создаст отступ, но FreeShow не разделит их на разные слайды
                if slide_parts:
                    # Соединяем разные текстовые блоки одного слайда через "-"
                    combined_block = "\n·\n".join(slide_parts)
                    # На всякий случай еще раз проверяем стык языков внутри блока
                    combined_block = re.sub(r'([а-яАЯёЁ])\s*\n\s*([a-zA-Z])', r'\1\n-\n\2', combined_block)
                    all_song_slides.append(combined_block)
            
            # Соединяем разные слайды тройным переносом (разделитель слайдов для FreeShow)
            if all_song_slides:
                txt_name = filename.replace(".pro6", ".txt")
                with open(os.path.join(output_folder, txt_name), 'w', encoding='utf-8') as f:
                    f.write("\n\n\n".join(all_song_slides))
                print(f"Успешно: {txt_name}")
                
        except Exception as e:
            print(f"Ошибка в файле {filename}: {e}")

print("\nВсё готово! Теперь импортируйте папку NewSongs во FreeShow как Text Files.")
