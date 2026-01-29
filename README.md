# 🔥 BAKASURA — AI-Powered OSINT Investigation Tool

<div align="center">

![Bakasura Logo](https://img.shields.io/badge/BAKASURA-OSINT_PROTOCOL-ff0055?style=for-the-badge&logo=skull&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.10+-blue?style=flat-square&logo=python)
![TypeScript](https://img.shields.io/badge/TypeScript-React-blue?style=flat-square&logo=typescript)
![Ollama](https://img.shields.io/badge/LLM-Ollama-green?style=flat-square)
![License](https://img.shields.io/badge/License-MIT-yellow?style=flat-square)

**Automated Open Source Intelligence gathering powered by local LLM**

[English](#english) | [Русский](#russian)

</div>

---

<a name="english"></a>
## 🇬🇧 English

### What is Bakasura?

**Bakasura** is an autonomous OSINT (Open Source Intelligence) agent that uses local LLM (via Ollama) to investigate individuals based on minimal initial data. Named after the demon from Hindu mythology who devours everything, this tool "consumes" publicly available data and produces structured intelligence dossiers.

### ✨ Key Features

- **🧠 AI-Powered Search** — Uses Qwen2.5:14B (or any Ollama model) to generate intelligent search queries and analyze results
- **🕸️ Snowball Protocol** — Iteratively expands investigation by finding new pivots (emails, usernames, phone numbers)
- **🔍 Maigret Integration** — Automatically scans 1000+ social platforms for username matches
- **🎭 Identity Filtering** — Smart filtering to avoid "namesake pollution" (people with similar names)
- **📝 Automatic Dossiers** — Generates Markdown reports compatible with Obsidian
- **🖥️ Modern UI** — Tauri-based desktop application with dark theme
- **🔒 100% Local** — All processing happens on your machine, no data leaves your computer

### 🛠️ Tech Stack

| Component | Technology |
|-----------|------------|
| **Backend** | Python 3.10+, FastAPI, LangGraph |
| **LLM** | Ollama (Qwen2.5:14B recommended) |
| **Scraping** | Playwright (headless browser) |
| **Social Scan** | Maigret CLI |
| **Frontend** | React + TypeScript + Tauri |
| **Storage** | Markdown files (Obsidian-compatible) |

### 📦 Installation

#### Prerequisites
- Python 3.10+
- Node.js 18+
- [Ollama](https://ollama.ai/) with `qwen2.5:14b` model
- Rust (for Tauri)

#### Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/yourusername/bakasura.git
cd bakasura

# 2. Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac

# 3. Install Python dependencies
pip install -r requirements.txt
pip install maigret playwright
playwright install chromium

# 4. Install Ollama model
ollama pull qwen2.5:14b

# 5. Install frontend dependencies
cd app
npm install

# 6. Run the application
cd ..
start_bakasura.bat  # Windows
# Or manually:
# Terminal 1: cd core && python main.py
# Terminal 2: cd app && npm run tauri dev
```

### 🎯 Usage

1. **Launch** the application using `start_bakasura.bat`
2. **Enter target data**:
   - Full Name (required)
   - City/Country (helps narrow down)
   - Phone Number (strong selector)
   - Nickname/Username (triggers Maigret scan)
   - Other clues
3. **Click "INITIATE PROTOCOL"**
4. **Wait** while the agent searches, scrapes, and analyzes
5. **View results** — dossier auto-opens in your Markdown editor

### 📁 Project Structure

```
bakasura/
├── app/                  # Frontend (React + Tauri)
│   ├── src/
│   └── src-tauri/
├── core/                 # Backend (Python)
│   ├── agent.py          # LangGraph workflow
│   ├── main.py           # FastAPI server
│   ├── scraper.py        # Playwright scraper
│   ├── search_tool.py    # Search engines integration
│   └── flowsint_tool.py  # Maigret wrapper
├── memories/             # Generated dossiers (Markdown)
├── config/               # Configuration files
└── start_bakasura.bat    # Windows launcher
```

### ⚙️ Configuration

Edit `config/mirrors.json` to add priority social media mirror sites:

```json
{
  "enable_mirrors": true,
  "social_mirrors": [
    "picuki.com",
    "imginn.com",
    "gramhir.com"
  ]
}
```

### ⚠️ Disclaimer

This tool is intended for **legal OSINT research only**. Users are responsible for ensuring their use complies with applicable laws and platform terms of service. The developers assume no liability for misuse.

---

<a name="russian"></a>
## 🇷🇺 Русский

### Что такое Bakasura?

**Bakasura** (Бакасура) — это автономный OSINT-агент, использующий локальную LLM (через Ollama) для исследования людей на основе минимальных начальных данных. Назван в честь демона из индуистской мифологии, пожирающего всё на своём пути — этот инструмент "поглощает" публично доступные данные и формирует структурированные разведывательные досье.

### ✨ Ключевые возможности

- **🧠 ИИ-поиск** — Использует Qwen2.5:14B (или любую модель Ollama) для генерации умных поисковых запросов и анализа результатов
- **🕸️ Протокол "Снежный ком"** — Итеративно расширяет расследование, находя новые зацепки (email, username, телефоны)
- **🔍 Интеграция Maigret** — Автоматическое сканирование 1000+ социальных платформ по никнейму
- **🎭 Фильтрация тёзок** — Умная фильтрация для избежания "загрязнения" данными однофамильцев
- **📝 Автоматические досье** — Генерирует Markdown-отчёты, совместимые с Obsidian
- **🖥️ Современный интерфейс** — Десктопное приложение на Tauri с тёмной темой
- **🔒 100% локально** — Вся обработка происходит на вашем компьютере

### 🛠️ Технологический стек

| Компонент | Технология |
|-----------|------------|
| **Бэкенд** | Python 3.10+, FastAPI, LangGraph |
| **LLM** | Ollama (рекомендуется Qwen2.5:14B) |
| **Скрапинг** | Playwright (headless браузер) |
| **Соц.сети** | Maigret CLI |
| **Фронтенд** | React + TypeScript + Tauri |
| **Хранение** | Markdown файлы (Obsidian-совместимые) |

### 📦 Установка

#### Требования
- Python 3.10+
- Node.js 18+
- [Ollama](https://ollama.ai/) с моделью `qwen2.5:14b`
- Rust (для Tauri)

#### Быстрый старт

```bash
# 1. Клонируем репозиторий
git clone https://github.com/yourusername/bakasura.git
cd bakasura

# 2. Создаём и активируем виртуальное окружение
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac

# 3. Устанавливаем Python-зависимости
pip install -r requirements.txt
pip install maigret playwright
playwright install chromium

# 4. Загружаем модель Ollama
ollama pull qwen2.5:14b

# 5. Устанавливаем зависимости фронтенда
cd app
npm install

# 6. Запускаем приложение
cd ..
start_bakasura.bat  # Windows
```

### 🎯 Использование

1. **Запустите** приложение через `start_bakasura.bat`
2. **Введите данные о цели**:
   - ФИО (обязательно)
   - Город/Страна (помогает сузить поиск)
   - Номер телефона (сильный идентификатор)
   - Никнейм/Username (запускает сканирование Maigret)
   - Другие зацепки
3. **Нажмите "INITIATE PROTOCOL"**
4. **Ожидайте** пока агент ищет, скрапит и анализирует
5. **Просмотрите результаты** — досье автоматически откроется в вашем редакторе

### 📁 Структура проекта

```
bakasura/
├── app/                  # Фронтенд (React + Tauri)
│   ├── src/
│   └── src-tauri/
├── core/                 # Бэкенд (Python)
│   ├── agent.py          # LangGraph воркфлоу
│   ├── main.py           # FastAPI сервер
│   ├── scraper.py        # Playwright скрапер
│   ├── search_tool.py    # Интеграция поисковиков
│   └── flowsint_tool.py  # Обёртка Maigret
├── memories/             # Сгенерированные досье (Markdown)
├── config/               # Конфигурационные файлы
└── start_bakasura.bat    # Лаунчер для Windows
```

### 🔧 API Ключи (опционально)

Для улучшения результатов можно добавить API ключи в настройках приложения:

- **Brave Search** — Улучшенный поиск
- **Exa (Metaphor)** — Семантический поиск
- **Hunter.io** — Поиск email по домену
- **HIBP** — Проверка утечек данных
- **Shodan** — Поиск по IP/устройствам

### ⚠️ Отказ от ответственности

Этот инструмент предназначен **исключительно для легального OSINT-исследования**. Пользователи несут ответственность за соблюдение применимых законов и условий использования платформ. Разработчики не несут ответственности за неправомерное использование.

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

<div align="center">

**Made with 🔥 by amritagopi**

*"The demon devours all data"*

</div>
