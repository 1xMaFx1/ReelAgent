# ReelAgent

## Текущая настройка: первый бесплатный выпуск

Репозиторий: https://github.com/1xMaFx1/ReelAgent

Двойной щелчок по **«Запустить ReelAgent.command»** запускает облачную задачу,
дожидается результата, скачивает MP4 в `output/` и открывает его только в Safari.
GitHub CLI установлен локально в `.local/bin`; авторизация хранится в системной связке ключей.

Для первого выпуска выбран `EPISODE_FILE=episodes/first-reel.json`: проверенный сценарий
о рассветах на МКС и официальные архивные видеокадры NASA. Этот режим не требует API-ключей
и не вызывает платные модели. Сценарий подготовлен заранее; новые сценарии в этом режиме
автоматически не придумываются. Повторный запуск в тот же день возвращает готовый ролик.

Google AI Studio перенаправил текущий аккаунт на страницу ограничений доступа.
GitHub Models не используется: сервис закрыт 30 июля 2026 года. Для новых автоматических
выпусков нужно подключить доступного LLM-провайдера и убрать `EPISODE_FILE`.

Расписание включается только переменной `DAILY_ENABLED=true` после подключения генерации.
Автопубликация требует однократной авторизации владельца канала. Без неё MP4 сохраняется,
но не выдаётся за опубликованный. Кнопка `Настроить ключи.command` принимает ключи скрытым
вводом и сохраняет их непосредственно в GitHub Secrets.

Чтобы ограничить накопление файлов, текущее состояние с роликом хранится 7 дней,
отдельный архив MP4 и логи — 1 день. Скачанные на Mac ролики остаются в `output/`.

ReelAgent собирает **один вертикальный ролик за сутки UTC**: русский сценарий, stock-видео Pexels, озвучка, крупные субтитры и монтаж FFmpeg. Результат — MP4 1080×1920, 30 fps, H.264/AAC, 30–45 секунд и `metadata.json`.

**Mac используется для разработки и проверки подключений. Рендер выполняется в GitHub Actions или на Linux-сервере.** На Mac команды `generate` и `run` блокируют новый монтаж. В Docker рендер включается только явной настройкой `APP_ENV=cloud`; используйте её на облачном сервере, не в Docker Desktop на Mac.

Сначала получите ролик без публикации. В исходной конфигурации `DRY_RUN=true`, обе площадки выключены. Программа не оформляет подписки, не подключает биллинг и не покупает API-кредиты.

## Быстрый путь к первому ролику

1. Получите ключи **Gemini** и **Pexels** по инструкции ниже.
2. Создайте на GitHub пустой репозиторий `ReelAgent`. Можно использовать private.
3. Загрузите в него содержимое этой папки вместе с `.github`, `.gitignore` и `.env.example`. Не загружайте `.env`.
4. В репозитории откройте **Settings → Secrets and variables → Actions → Secrets**. Добавьте `GEMINI_API_KEY` и `PEXELS_API_KEY`.
5. Откройте **Actions → Daily Reel → Run workflow**, выберите `generate`.
6. Дождитесь завершения. Внизу страницы запуска, в **Artifacts**, скачайте `reel-<номер>-<попытка>`.
7. Распакуйте архив: внутри папка даты, `reel.mp4`, `metadata.json`, `subtitles.ass`. Откройте MP4 обычным видеоплеером.

Без ключей Gemini/Pexels реальный тематический MP4 создать нельзя. Тесты используют подмены API и не создают настоящий ролик. Отдельный workflow **Tests** умеет проверять монтаж на синтетических кадрах в облаке без ключей.

## Как работает pipeline

```text
Gemini
  ↓
Script (hook + 4–7 сцен + ending)
  ↓
Pexels (уникальные клипы; fallback на фотографии)
  ↓
TTS (русский голос через edge-tts)
  ↓
Subtitles (ASS, временные отметки слов)
  ↓
FFmpeg (облачный runner)
  ↓
MP4 + metadata.json + SQLite
  ↓
YouTube / Instagram через Cloudinary (по желанию)
```

Технически озвучка создаётся до загрузки кадров: её фактическая длительность задаёт тайминг. Hook и ending входят в полную озвучку ровно один раз; для них используются первый и последний клип. Кадры обрезаются по длительности, короткие клипы зацикливаются. Масштабирование с crop заполняет экран без чёрных полос.

Скорость голоса при необходимости корректируется в пределах 0.75–1.35, чтобы уложиться в 30–45 секунд. Сильно неподходящий сценарий вызывает понятную ошибку вместо неестественно ускоренного голоса. Субтитры синхронизируются с тем же коэффициентом. Если TTS не вернул отметки слов, применяется приблизительный тайминг по известному тексту. Модельная оценка `duration` сохраняется отдельно от фактического `render_duration`.

Тематика ограничена наукой, космосом, природой, технологиями и автомобилями. Есть отдельная модельная проверка допустимости сценария. Это не полноценная проверка фактов: перед включением автопубликации просмотрите несколько выпусков.

## Архитектура и файлы

```text
ReelAgent/
├── app/
│   ├── main.py                 # CLI
│   ├── config.py               # настройки из .env
│   ├── core/
│   │   ├── models.py           # Pydantic + статусы
│   │   ├── pipeline.py         # оркестрация
│   │   ├── database.py         # SQLite и уникальный день
│   │   ├── timing.py           # длительности озвучки и сцен
│   │   └── logger.py           # ротация и удаление секретов из логов
│   ├── llm/                   # LLMProvider, GeminiProvider
│   ├── media/                 # VideoProvider, Pexels, загрузчик
│   ├── tts/                   # TTSProvider, EdgeTTSProvider
│   ├── subtitles/             # SubtitleGenerator
│   ├── video/                 # VideoComposer, FFmpeg
│   ├── storage/               # StorageProvider, Cloudinary
│   ├── publishers/            # Publisher, YouTube, Instagram
│   └── utils/                 # JSON, retries, блокировка
├── scripts/
│   ├── cloud_state.py         # восстановление истории из Artifact
│   └── smoke_render.py        # облачный тест монтажа без ключей
├── tests/                     # unit-тесты без внешних API
├── assets/music/              # необязательная музыка
├── data/tmp/                  # временные файлы
├── data/reelagent.db           # появляется после первого запуска
├── output/YYYY-MM-DD/         # MP4, metadata, ASS
├── logs/reelagent.log
├── .github/workflows/
│   ├── daily-reel.yml
│   └── tests.yml
├── .env.example
├── .gitignore
├── .dockerignore
├── requirements.txt
├── requirements-dev.txt
├── constraints.txt            # версии, использованные при проверке
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
└── README.md
```

Интерфейсы описаны через `Protocol`. Для другого LLM, TTS или видеопровайдера добавьте реализацию интерфейса и подключите её в pipeline. Пока существует один канал; для нескольких каналов потребуется составной ключ `(channel_id, day)` в БД и отдельные настройки. Redis, Celery, локальные модели и веб-интерфейс не используются.

## Установка на Mac: разработка без рендера

Понадобится Python 3.12 или новее. Откройте Terminal:

```bash
cd ~/Desktop/ReelAgent
python3 --version
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
cp .env.example .env
```

Откройте `.env` текстовым редактором. Вставьте ключи после знака `=`. Не добавляйте их в Python-файлы. `.env` уже исключён из Git. Запускайте команды из папки проекта — пути считаются от неё.

```bash
python -m app.main --help
python -m pytest -q
python -m app.main test-llm
python -m app.main test-pexels
python -m app.main test-tts
```

- `test-llm`: один запрос на тему; нужен ключ Gemini.
- `test-pexels`: поиск без скачивания видео; нужен ключ Pexels.
- `test-tts`: короткий запрос к удалённому сервису, результат `data/tmp/tts-test.mp3`. API-ключ не нужен.
- Unit-тесты не отправляют запросы и не запускают FFmpeg.

FFmpeg на Mac для этих команд не требуется. `edge-tts` синтезирует речь на удалённом сервисе; локально сохраняется только MP3.

## Gemini API key

Откройте [Google AI Studio](https://aistudio.google.com/apikey), создайте API key и сохраните его как `GEMINI_API_KEY`. Если бесплатная квота доступна вашему аккаунту и региону, используйте её. Условия, регионы и модели могут меняться; наличие ключа само по себе не гарантирует бесплатный доступ.

В примере задан `GEMINI_MODEL=gemini-2.5-flash`. Проверьте доступность этой модели в AI Studio; при необходимости укажите актуальную модель с поддержкой structured JSON output. Проект использует REST `generateContent`, а не SDK с меняющимися методами. [Документация JSON Schema](https://ai.google.dev/gemini-api/docs/generate-content/structured-output).

Ответы валидируются Pydantic. Удаляется Markdown-обёртка или текст вокруг JSON; затем допускаются максимум два повторных запроса. Общий бюджет с сетевыми ошибками — три попытки на запрос, с exponential backoff через tenacity. Ошибки ключа и доступа не повторяются бессмысленно.

## Pexels API key

На [странице Pexels API](https://www.pexels.com/api/) создайте аккаунт и запросите ключ. Вставьте его в `PEXELS_API_KEY`. Используется [официальный API](https://www.pexels.com/api/documentation/), поиск portrait-видео. При отсутствии подходящих результатов запрос упрощается, затем ищется фотография. Один Pexels ID не используется дважды внутри ролика.

Ссылки на оригиналы и имена авторов сохраняются в `metadata.json → sources`. Проверяйте условия использования выбранного материала; stock-кадр может быть иллюстрацией темы, а не документальной съёмкой описываемого события.

## GitHub Actions: настройка

При использовании Git из Terminal (после создания пустого репозитория):

```bash
cd ~/Desktop/ReelAgent
git init -b main
git add .
git commit -m "Initial ReelAgent MVP"
git remote add origin https://github.com/YOUR_USERNAME/ReelAgent.git
git push -u origin main
```

Замените `YOUR_USERNAME` своим именем GitHub. Команда push может запросить вход в GitHub. Перед `git add` убедитесь, что `.gitignore` присутствует. Папка `.github` скрыта в Finder; загрузка через Git включает её автоматически.

Workflow использует Ubuntu и Python 3.12, устанавливает FFmpeg и шрифт DejaVu Sans, запускает Python CLI. Вам не требуется арендовать сервер для этого варианта. Доступные бесплатные минуты и хранилище зависят от плана GitHub: [billing Actions](https://docs.github.com/en/billing/concepts/product-billing/github-actions).

### Secrets

**Settings → Secrets and variables → Actions → Secrets → New repository secret**:

| Имя | Для чего |
| --- | --- |
| `GEMINI_API_KEY` | Обязательно: сценарий |
| `PEXELS_API_KEY` | Обязательно: видеоряд |
| `YOUTUBE_CLIENT_ID` | YouTube OAuth, необязательно |
| `YOUTUBE_CLIENT_SECRET` | YouTube OAuth, необязательно |
| `YOUTUBE_REFRESH_TOKEN` | YouTube OAuth, необязательно |
| `INSTAGRAM_ACCESS_TOKEN` | Instagram, необязательно |
| `INSTAGRAM_ACCOUNT_ID` | ID профессионального Instagram, необязательно |
| `CLOUDINARY_CLOUD_NAME` | Cloudinary для Instagram |
| `CLOUDINARY_API_KEY` | Cloudinary для Instagram |
| `CLOUDINARY_API_SECRET` | Cloudinary для Instagram |

Не требуется переносить `.env` в GitHub. Workflow читает Secrets непосредственно. `GH_TOKEN` для восстановления истории выдаётся GitHub автоматически и не является персональным токеном.

### Variables

В соседней вкладке **Variables** можно задать:

| Имя | Значение по умолчанию |
| --- | --- |
| `GEMINI_MODEL` | `gemini-2.5-flash` |
| `TTS_VOICE` | `ru-RU-DmitryNeural` |
| `DRY_RUN` | `true` |
| `AUTO_PUBLISH_YOUTUBE` | `false` |
| `AUTO_PUBLISH_INSTAGRAM` | `false` |
| `YOUTUBE_PRIVACY_STATUS` | `public` |
| `INSTAGRAM_API_VERSION` | `v24.0` |

Для первого опыта оставьте DRY_RUN включённым. Другие настройки `.env.example` можно передать через секцию `env` workflow, если потребуется изменить оформление.

## Ручной и ежедневный запуск

**Actions → Daily Reel → Run workflow → generate** создаёт ролик без публикации независимо от флагов.

Выбор **run** учитывает `DRY_RUN` и флаги площадок. Запуск без команды, `python -m app.main`, эквивалентен `run`.

Расписание в `.github/workflows/daily-reel.yml`:

```yaml
schedule:
  - cron: '17 7 * * *'
```

Это ежедневно в **07:17 UTC**. Для UTC+3 — 10:17. Измените первые два числа: сначала минуты, потом часы UTC. GitHub запускает расписание из default branch; cron может стартовать с задержкой. В публичном репозитории расписание может отключиться после длительного отсутствия активности. [Правила scheduled workflows](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

Гарантия MVP — **не более одного готового ролика за день UTC при сохранённой истории**. Один успешный выпуск ежедневно зависит от доступности API, квот и runner. Сбой генерации допускает повторную попытку в тот же день. Если ролик уже готов, повторный запуск использует его, а не генерирует новый.

SQLite и текущий ролик сохраняются в Artifact `reelagent-state` на 90 дней. Перед следующим запуском восстанавливаются БД и только файлы текущей даты. Это сохраняет последние 100 тем и защиту от дублей между отдельными runner. Локальная БД без такого восстановления не пережила бы смену runner.

Не удаляйте самый свежий state artifact. При обнаруженной утрате истории workflow останавливается. После длительной паузы восстановите последнюю резервную копию. Аварийная остановка runner до сохранения Artifact не даёт строгой exactly-once гарантии внешней публикации; перед перезапуском после такого сбоя проверьте аккаунты.

## Как проверить первый MP4

Откройте видео из Artifact и проверьте:

- вертикальный кадр 1080×1920, без чёрных полос;
- понятный hook, русский голос, конец фразы не обрезан;
- крупные субтитры, не более двух строк, без перекрытия интерфейсом площадки;
- кадры соответствуют теме, факты корректны;
- длительность 30–45 секунд.

`metadata.json` содержит полный текст, заголовок, описание, хештеги, сцены, фактическую длительность, источники кадров, результаты публикации и отметки попыток. `youtube` и `instagram` равны `null`, пока публикации нет. `subtitles.ass` также сохраняется для проверки.

FFmpeg автоматически проверяет кодеки, размеры кадра и длительность через ffprobe перед переименованием временного файла в `reel.mp4`.

## YouTube setup

1. Откройте [Google Cloud Console](https://console.cloud.google.com/), создайте проект и включите **YouTube Data API v3**.
2. Настройте OAuth consent screen. Если приложение в Testing, добавьте свой Google-аккаунт в Test users.
3. Создайте OAuth client типа **Web application**. Для получения токена через [OAuth Playground](https://developers.google.com/oauthplayground/) добавьте redirect URI `https://developers.google.com/oauthplayground`.
4. В настройках Playground включите **Use your own OAuth credentials**, введите Client ID и Client Secret.
5. Укажите scope `https://www.googleapis.com/auth/youtube.upload`, выполните Authorize APIs, войдите в аккаунт нужного YouTube-канала.
6. Выполните **Exchange authorization code for tokens**. Сохраните refresh token в `YOUTUBE_REFRESH_TOKEN`, а credentials — в соответствующие Secrets.
7. Для первого теста задайте `YOUTUBE_PRIVACY_STATUS=private`, `AUTO_PUBLISH_YOUTUBE=true`, `DRY_RUN=false`. Запустите workflow в режиме `run`.
8. После проверки можно установить `YOUTUBE_PRIVACY_STATUS=public`.

Используется resumable upload через httpx: при временной ошибке проверяется та же upload session, чтобы не создать второй ролик. Access token обновляется через refresh token. [OAuth offline access](https://developers.google.com/identity/protocols/oauth2/web-server#offline).

У OAuth-приложений в Testing срок жизни refresh token может быть ограничен; для постоянной автоматизации настройте соответствующий publishing status приложения и требования Google. YouTube также ограничивает ролики от непроверенных API-проектов приватным доступом до аудита: [videos.insert](https://developers.google.com/youtube/v3/docs/videos/insert). Флаг `public` не отменяет это ограничение.

Shorts не требует отдельного upload endpoint: передаётся обычный вертикальный короткий MP4. Классификация выполняется YouTube.

## Instagram и Cloudinary setup

Реализован вариант **Instagram API with Facebook Login**, с адресом `graph.facebook.com`. Не смешивайте его с токенами Instagram Login и адресом `graph.instagram.com`.

1. Нужен профессиональный Instagram-аккаунт (Business/Creator), связанный с Facebook Page.
2. В [Meta for Developers](https://developers.facebook.com/) создайте приложение с соответствующим Instagram use case и подключите аккаунт.
3. Настройте Facebook Login и разрешения `instagram_basic`, `instagram_content_publish`, `pages_show_list`, `pages_read_engagement` согласно доступной в вашем приложении схеме разрешений. Для чужих аккаунтов может потребоваться App Review и Advanced Access.
4. В Graph API Explorer получите токен с нужными разрешениями для пользователя, управляющего Page. Запрос `GET /me/accounts?fields=id,name,instagram_business_account` помогает найти Instagram account ID связанной страницы; при необходимости запросите `/{PAGE_ID}?fields=instagram_business_account`.
5. Сохраните нужный долгоживущий токен как `INSTAGRAM_ACCESS_TOKEN`, Instagram ID — как `INSTAGRAM_ACCOUNT_ID`. Отслеживайте срок жизни токена: автоматическое обновление Meta-токенов в MVP не реализовано.
6. Проверьте доступную версию Graph API в Meta dashboard; при необходимости измените `INSTAGRAM_API_VERSION`. Пример использует `v24.0`.
7. Создайте аккаунт [Cloudinary](https://cloudinary.com/), скопируйте Cloud Name, API Key, API Secret из dashboard. Выберите бесплатный план, если он подходит по квотам; проверьте лимиты хранения и трафика.
8. Добавьте Cloudinary Secrets, затем `AUTO_PUBLISH_INSTAGRAM=true` и `DRY_RUN=false`. Запустите `run`.

Поток публикации: подписанная загрузка MP4 в Cloudinary → HTTPS URL → создание `REELS` container → ожидание `FINISHED` → `media_publish`. Ожидание обработки ограничено пятью минутами. Cloudinary-файлы не удаляются автоматически: контролируйте квоту и удаляйте старые после проверки публикации. В MVP обычная загрузка ограничена 95 MB; для больших файлов потребуется chunked upload.

[Официальная документация Meta](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-facebook-login/content-publishing/) и [Cloudinary Upload API](https://cloudinary.com/documentation/image_upload_api_reference). Детали разрешений и доступ к приложению необходимо подтвердить в вашем Meta dashboard; интеграция без ваших credentials не проверена на настоящем аккаунте.

## Docker и обычный Python в облаке

На облачном Linux-сервере скопируйте проект и создайте `.env` из примера. Установите `APP_ENV=cloud`, вставьте ключи, сохраните `DRY_RUN=true` для первого запуска.

Docker:

```bash
docker compose build
docker compose run --rm reelagent generate
# После настройки публикации:
docker compose run --rm reelagent run
```

Обычный Python на Ubuntu:

```bash
sudo apt-get update
sudo apt-get install -y ffmpeg fonts-dejavu-core
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.main generate
# Или с публикацией согласно .env:
python -m app.main run
```

Для Python необходима версия 3.12+. На сервере без этой версии используйте Docker. Запускайте один экземпляр с общей папкой `data`; дополнительно действует файловая блокировка. На Linux-сервере расписание можно настроить отдельно, но готовый ежедневный scheduler в проекте — GitHub Actions.

## Музыка и оформление

Положите лицензированный трек MP3/WAV/M4A/OGG в `assets/music/`. Если папка пуста, музыки нет. При наличии нескольких выбирается случайный; он зацикливается, нормализуется и микшируется с громкостью около 10% от нормализованного голоса, с fade in/out. Музыка автоматически не скачивается.

Изменяемые настройки в `.env.example`: голос, шрифт, размер текста, отступ снизу, ширина строки, громкость музыки, размеры и fps. Для Shorts/Reels сохраните стандартные 1080×1920 и 30 fps.

## Ошибки, статусы и повторная публикация

`CREATED → GENERATING → RENDERING → READY → PUBLISHED`.

Ошибка до готового MP4 даёт `FAILED`. Ошибка одной публикации оставляет `READY` или `PARTIALLY_PUBLISHED`; другая площадка всё равно получает свою попытку. Отсутствующая авторизация выводит `Publishing disabled`, не мешая создать видео. После успешного монтажа временные материалы удаляются; при ошибке рендера остаются для диагностики.

Повторные сетевые запросы: до трёх попыток с exponential backoff. Для YouTube/Instagram финальная публикация использует проверки состояния, поскольку слепое повторение POST может создать дубликат. Перед попыткой в metadata сохраняется `publication_attempts`. Уже успешная или неопределённая попытка не повторяется при новом запуске.

Если публикация завершилась неопределённо, сначала проверьте YouTube Studio / Instagram. Если ролик существует, сохраните его ID в соответствующем поле metadata. Если его точно нет, можно удалить только отметку нужной площадки из `publication_attempts`, исправить настройки и повторить `run` в ту же дату при сохранённых MP4/metadata. Это ручная операция восстановления для разработчика. В первой версии отдельной команды повторной публикации старых дат нет; старый ролик можно загрузить вручную.

## Troubleshooting

| Симптом | Что проверить |
| --- | --- |
| `Render is cloud-only` | На Mac это ожидаемо. Запускайте Daily Reel в GitHub Actions; на облачном Linux задайте APP_ENV=cloud |
| `Missing settings` | Названия Secrets и ключи Gemini/Pexels |
| Gemini rejected request | Ключ, доступность региона/модели, квоту; `GEMINI_MODEL` в Variables |
| Invalid JSON after 3 attempts | Модель должна поддерживать structured JSON; повторите позже или смените модель |
| Narration is too short/long | Сценарий сильно не подходит по темпу; повторите генерацию после неуспешного запуска |
| Pexels 401/429 | Неверный ключ или лимит API |
| Нет уникальных материалов | Более общий английский visual query; fallback уже пробует фото |
| TTS недоступен | Доступ к сервису Edge, актуальную версию edge-tts, корректное имя голоса |
| Нет FFmpeg/ASS | Используйте готовый workflow/Docker; FFmpeg должен быть собран с libass, шрифт установлен |
| Publishing disabled | DRY_RUN, AUTO_PUBLISH, наличие всех credentials; команда generate никогда не публикует |
| YouTube остаётся private | Аудит Google API project, privacy status и OAuth |
| Instagram отказал | Тип аккаунта, связь Page, scopes, срок токена, версия API |
| Instagram processing timeout | Доступность публичного HTTPS URL, формат MP4 и состояние контейнера |
| Ролик за сегодня уже существует | Это защита от дубля; скачайте Artifact или используйте существующий MP4 |
| State artifact missing/expired | Восстановите SQLite из резервной копии, не сбрасывайте историю для обхода проверки |
| Ошибка рендера | `logs/reelagent.log`; на сервере также `data/tmp/` |
| Не запускается cron | Default branch, включённые Actions, состояние расписания и квоты runner |

Логи ротируются, API-ключи и URL скрываются. Не включайте отладочную печать объектов настроек или тел OAuth-ответов. `.env`, SQLite, выходные и временные файлы исключены из Git.

## Проверка разработки

```bash
python -m pytest -q
ruff check app tests scripts
python -m compileall -q app scripts
```

В GitHub workflow **Tests** дополнительно запускает настоящий короткий синтетический FFmpeg render 360×640 с русскими ASS-субтитрами, без API-ключей. Основной ролик всегда использует стандартные 1080×1920, если настройки не менялись. Тестовое видео временное и не выдаётся за выпуск ReelAgent.

`constraints.txt` фиксирует версии зависимостей, использованные при проверке. Обновляйте их осознанно и затем повторяйте тесты. Проект не содержит тяжёлых генеративных моделей, Whisper или MoviePy.
