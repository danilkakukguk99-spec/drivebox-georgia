const DRIVEBOX_GALLERIES = {
  "compressor": [
    "assets/products/compressor-1.jpg",
    "assets/products/compressor-2.jpg"
  ],
  "headlight-kit": [
    "assets/products/headlight-kit-1.webp",
    "assets/products/headlight-kit-2.png"
  ],
  "carplay": [
    "assets/products/carplay-1.jpg",
    "assets/products/carplay-2.jpg",
    "assets/products/carplay-3.jpg"
  ],
  "dashcam": [
    "assets/products/dashcam-1.jpg",
    "assets/products/dashcam-2.jpg"
  ],
  "charger-holder": [
    "assets/products/charger-holder-1-clean.png",
    "assets/products/charger-holder-2-clean.png",
    "assets/products/charger-holder-3-clean.png"
  ],
  "vacuum": [
    "assets/products/vacuum-1-clean.png",
    "assets/products/vacuum-2-clean.png"
  ],
  "jumpstarter": [
    "assets/products/jumpstarter-1-clean.png",
    "assets/products/jumpstarter-2-clean.png"
  ]
};
window.DRIVEBOX_PRODUCTS.forEach(p=>{if(DRIVEBOX_GALLERIES[p.id]){p.gallery=DRIVEBOX_GALLERIES[p.id];p.image=p.gallery[0]}});
