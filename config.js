window.DRIVEBOX_CONFIG = {
  brand: "DRIVEBOX",
  domain: "drivebox.ge",
  defaultLanguage: "ka",
  testMode: true,
  promotion: { enabled: true, discountPercent: 15, freeShipping: true },
  seller: {
    legalName: "REPLACE_WITH_SELLER_NAME",
    idNumber: "REPLACE_WITH_IE_ID",
    address: "Tbilisi, Georgia",
    phone: "+995 5XX XX XX XX",
    whatsapp: "9955XXXXXXXX",
    email: "hello@drivebox.ge"
  },
  paypal: {
    clientId: "REPLACE_WITH_PAYPAL_CLIENT_ID",
    currency: "USD",
    // PayPal standard checkout does not currently support GEL as a payment balance currency.
    // Site prices stay in GEL; checkout converts to USD using this manual rate.
    gelPerUsd: 2.70
  },
  shipping: {
    tbilisiSameDay: 9,
    tbilisiNextDay: 7,
    regions: 12,
    freeFrom: 250,
    sameDayCutoffHour: 15
  },
  analytics: {
    metaPixelId: "",
    tiktokPixelId: "",
    ga4Id: ""
  }
};
