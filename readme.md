# DRIVEBOX prototype

Static, mobile-first Georgia automotive-accessories store prototype.

## Included
- Georgian default language + Russian + English switcher
- One store, seven dedicated product landing pages
- Shared cart + checkout
- PayPal JS SDK integration scaffold
- Same-day / next-day delivery pricing config
- Seller info, terms, delivery, returns and privacy pages
- Supplier/reference product images for prototype use
- UTM-friendly direct product URLs

## Critical before going live
1. Edit `config.js`: seller legal name, IE/tax ID, address, phone, WhatsApp, email.
2. Set `testMode: false` only after the seller setup and payment flow are ready.
3. Insert PayPal Business Client ID. Do NOT use Friends & Family for product sales.
4. PayPal: site can show GEL, but standard PayPal payment currencies currently do not list GEL. This prototype converts the cart to USD using `gelPerUsd`. Replace the manual FX logic with a controlled live process before production.
5. Product photos are linked from supplier/market pages for a prototype only. Obtain written permission/licensing from the supplier/rightsholder before commercial publication or replace them with your own photos/UGC.
6. Confirm actual B2B prices, stock, one-unit pickup, neutral packaging, invoice policy and courier handoff with each supplier.
7. CarPlay and Dashcam supplier status is not yet wholesale-confirmed; those entries are retail market references.
8. Replace draft legal pages with final Georgian-language consumer terms for the exact seller and fulfillment process.
9. Add a real backend/order database + server-side PayPal webhook before production. Client-side-only capture is insufficient for reliable fulfillment.
10. Add Meta/TikTok/GA pixels only together with the live privacy/cookie implementation.

## Run locally
From the site folder:

```bash
python3 -m http.server 8000
```
Then open http://localhost:8000

## Easy deployment
The folder can be deployed as a static site to Netlify, Cloudflare Pages, GitHub Pages, Vercel static hosting, or any ordinary web host. PayPal itself can render client-side, but production order verification should have a backend/serverless function.

## Product image/source references
- Avtospar 15W holder: https://avtospar.ge/products/233
- Avtospar 120W vacuum: https://avtospar.ge/products/159
- Avtospar KS-312: https://avtospar.ge/products/ks-312
- AutoMenu T-Cut headlight kit: https://automenu.ge/ka/product/ფარების-აღდგენის-ნაკრები/
- BestEnergy / Akumulatori.ge NOCO: https://akumulatori.ge/en/noco
- CarPlay market reference: https://mymarket.ge/pr/31625403/
- Dashcam retail reference: https://zoommer.ge/en/monitoring/xiaomi-70mai-dash-cam-a410-set-black-p51678
