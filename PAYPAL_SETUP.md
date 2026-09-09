# DRIVEBOX — PayPal Sandbox и Live

## Архитектура и изменения

Сохранён существующий checkout: HTML/JS → Python WSGI → SQLite. Новый параллельный магазин или Netlify Functions не создавались. Размещение рассчитано на существующий Python backend с постоянным диском (Gunicorn/Docker); статический хостинг сам по себе не обслужит оплату.

Изменены `server/store.py`, `commerce.js`, `checkout.html`, `order.html`, `payments.js`, `admin.js`, `styles.css`, подключения скриптов общих страниц, `.env.example`, тесты и эта инструкция. Исходная вёрстка hero и карточек товаров сохранена.

## Что реализовано

- На checkout отдельные варианты «Банковская карта · Visa / Mastercard», PayPal и оплата при получении. COD включён для локальной проверки и не вызывает PayPal.
- PayPal JS SDK v6. Для карты сначала проверяется `advanced_cards` и используются PayPal-hosted Card Fields. Если они недоступны, проверяется `card` и используется гостевая форма PayPal. Если оба варианта недоступны, предлагаем альтернативу без обещания оплаты картой.
- Обычная PayPal-кнопка запускает отдельную PayPal-сессию.
- После заполнения данных и сохранения заказа клиент переходит на существующую страницу заказа для оплаты. Карточные поля находятся только в iframe PayPal. Номер карты, CVV и срок действия не читаются, не отправляются в API магазина и не хранятся в базе.
- `/api/orders` рассчитывает товары, скидку, доставку и итог из серверного каталога и фиксирует сумму заказа.
- `POST /api/paypal/create-order` принимает ID локального заказа и его закрытый token; сумма берётся из уже рассчитанного сервером неизменяемого заказа. Возвращается только `orderId` PayPal.
- `POST /api/paypal/capture-order` принимает локальный ID/token и `orderId` PayPal. Проверяются принадлежность заказа, ID PayPal, intent, reference/custom ID, сумма и валюта заказа и capture, capture ID и COMPLETED. Payer ID/email сохраняются, когда PayPal их возвращает (для гостевой карты могут отсутствовать).
- `POST /api/paypal/cancel-order` записывает отмену покупателем, но не препятствует более позднему подтверждению реально завершённого платежа.
- Повторы create/capture имеют постоянный PayPal-Request-Id. Существующий оплаченный заказ не вызывает повторный capture. После неопределённого create старше 5 часов автоматическое создание блокируется для ручной проверки.
- Сумма магазина — GEL, списание PayPal — USD по `GEL_PER_USD`, фиксируется при создании заказа и показывается до оплаты. Автоматического рыночного курса нет.
- Корзина очищается от заказанных позиций после подтверждённой оплаты или принятого COD. Отмена, неуспех и сетевые ошибки не очищают её.
- Статусы: pending, paid, failed, cancelled, cash_on_delivery, refunded, partially_refunded, review_required. Статус доставки независим.

## Подключение Sandbox

1. Открыть https://developer.paypal.com/dashboard/applications/sandbox.
2. В Apps & Credentials выбрать Sandbox, создать/выбрать REST app Sandbox Business-продавца.
3. В локальном `.env` или секретах хостинга установить:

```dotenv
PAYPAL_ENV=sandbox
PAYPAL_CLIENT_ID=<Sandbox Client ID>
PAYPAL_CLIENT_SECRET=<Sandbox Secret>
PAYPAL_WEBHOOK_ID=<Sandbox webhook ID>
ALLOW_COD=true
GEL_PER_USD=2.70
PUBLIC_URL=https://ваш-тестовый-домен
APP_ENV=development
```

Client ID публичный: его получает SDK. Secret используется только Python backend. Не помещать секрет в `config.js`, frontend или Git.

Для localhost можно оставить `PUBLIC_URL=http://localhost:8000`: это локальная проверка, а не production. Для проверки webhook нужен доступный PayPal публичный HTTPS-адрес, обслуживающий этот же backend. Сам localhost PayPal не увидит. Не публикуйте каталог `.env`, `data` или `server` статическим сервером.

4. В Sandbox Accounts создать отдельного Personal-покупателя. Не использовать реальную карту в Sandbox; брать тестовые карточные данные из официальных средств PayPal Sandbox.
5. Для embedded card fields проверить доступность Advanced/Expanded Card Payments для Business-аккаунта. Account Optional не гарантирует доступность конкретного метода для всех покупателей; интерфейс проверяет eligibility SDK.
6. Перезапустить сервер после изменения `.env`.

## Webhook

URL: `https://ваш-домен/api/paypal/webhook`.

Выбрать:

- CHECKOUT.ORDER.APPROVED
- PAYMENT.CAPTURE.COMPLETED
- PAYMENT.CAPTURE.PENDING
- PAYMENT.CAPTURE.DENIED
- PAYMENT.CAPTURE.REFUNDED
- PAYMENT.CAPTURE.REVERSED

Ввести ID созданного webhook в `PAYPAL_WEBHOOK_ID`. Подпись проверяется PayPal verify-webhook-signature; неверные сообщения отклоняются. Повторы событий не дублируют возврат или оплату. Completed/Approved перепроверяются через Orders API. Refund сопоставляется с сохранённым capture ID, проверяются валюта и сумма; частичные возвраты суммируются по уникальным refund ID. Позднее событие completed не отменяет статус возврата.

Для локальных Sandbox create/capture достаточно Client ID и Secret; отсутствие webhook нужно устранить до его проверки и перед Live. Live требует настроенного webhook.

## Проверки: что выполнено, что ещё нужно

Выполнены локально 39 серверных тестов и 8 JS-тестов с имитацией SDK. В них проверены серверные цены, подмена суммы/валюты/ID, конкурентное создание, повторный capture, approved без completed, timeout с последующим подтверждением, отмена, отказ, подпись webhook, полный возврат и повторы, COD без PayPal, eligibility и callback-интерфейс.

Это НЕ реальные транзакции Sandbox. Без Sandbox credentials остаются непроверенными:

- Успешная оплата PayPal аккаунтом Sandbox Personal.
- Успешная карта, гостевая форма, 3DS и доступность карты для конкретного Business-аккаунта.
- Реальные cancel/decline и повтор оплаты в интерфейсе PayPal.
- Доставка подписанного webhook на ваш HTTPS-домен.
- Закрытие/обновление вкладки и восстановление на реальном провайдере.

Тестовые заказы должны оставаться отделены от production. Для Live используйте отдельную новую базу. Старые неоплаченные PayPal-заказы, созданные предыдущей интеграцией без привязки к environment/account, блокируются от оплаты; оформите новый Sandbox-заказ.

Команды:

```sh
python3 -m unittest discover -s tests -v
node tests/payment_ui.test.cjs
git diff --check
```

## Переход на Live — только после Sandbox

1. Заполнить остальные настройки магазина из DEPLOYMENT.md, подтвердить реальные условия доставки/COD и юридические тексты.
2. Использовать публичный HTTPS-домен и production-базу на постоянном диске.
3. В PayPal Dashboard переключить Apps & Credentials на Live. Использовать Live Business-приложение.
4. Заменить `PAYPAL_CLIENT_ID` и `PAYPAL_CLIENT_SECRET` на Live credentials, установить `PAYPAL_ENV=live`, `APP_ENV=production`.
5. Создать отдельный Live webhook на том же production URL с указанными событиями. Заменить `PAYPAL_WEBHOOK_ID`.
6. Перезапустить web-процесс и worker. SDK выбирает Live URL по environment; сервер выбирает соответствующий REST API. Sandbox-заказы не оплачиваются Live-ключами.
7. Проверить небольшой реальный заказ и возврат владельцем магазина. Автоматическое переключение Live и реальные списания в этой работе не выполняются.

Возвраты денег выполняются в кабинете PayPal; магазин получает их подтверждение через webhook. Кнопки автоматического возврата в админке нет.

## Официальные источники

- SDK v6 setup: https://developer.paypal.com/sdk/js/set-up
- SDK v6, hosted fields, guest sessions: https://developer.paypal.com/sdk/js/reference/
- Orders API: https://developer.paypal.com/docs/api/orders/v2/
- Webhooks: https://developer.paypal.com/api/rest/webhooks/
- Idempotency: https://developer.paypal.com/reference/guidelines/idempotency/
