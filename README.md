# Queue Bot — очередь для группы

Telegram-бот для управления очередями по предметам.

## Предметы
- Методы и средства проектирования ИС и Т
- Технологии Front-end разработки веб-приложений
- Современные операционные системы
- Администрирование баз данных

## Функции
- Встать / выйти из очереди по каждому предмету
- Пропустить свой ход (поменяться со следующим)
- Уведомления: ты стал первым, кто-то встал за тобой, кто-то пропустил ход

---

## Деплой на Railway

### 1. Создать бота
1. Открыть [@BotFather](https://t.me/BotFather) в Telegram
2. `/newbot` → задать имя и username
3. Скопировать токен вида `123456789:AAF...`

### 2. Загрузить код на GitHub
```bash
git init
git add .
git commit -m "init"
git remote add origin https://github.com/YOUR/queue-bot.git
git push -u origin main
```

### 3. Создать проект на Railway
1. Зайти на [railway.app](https://railway.app) → New Project → Deploy from GitHub repo
2. Выбрать репозиторий
3. Перейти в Variables → добавить переменную:
   - `BOT_TOKEN` = твой токен от BotFather

### 4. Запуск
Railway автоматически запустит `worker: python bot.py` из Procfile.

> ⚠️ Состояние очереди хранится в `state.json` в памяти контейнера.
> При рестарте сервиса очереди сбросятся. Для постоянного хранения
> можно подключить Railway PostgreSQL или Redis (по запросу).

---

## Локальный запуск (для теста)
```bash
pip install -r requirements.txt
BOT_TOKEN=ваш_токен python bot.py
```
