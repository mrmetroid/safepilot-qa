// Harbor Roast store logic: localStorage cart, harmless dummy flows. No real data is collected.
const PRODUCTS = [
  { id: 'harbor-blend', name: 'Harbor Blend', price: 14, color: '#7a4b2a', blurb: 'Chocolate, toasted almond, sea-salt finish.' },
  { id: 'north-light', name: 'North Light Espresso', price: 16, color: '#3d2416', blurb: 'Dense crema, dark cherry, cocoa nib.' },
  { id: 'fika-decaf', name: 'Fika Decaf', price: 13, color: '#b07d4f', blurb: 'Swiss water decaf, caramel and oat.' },
];

const Cart = {
  get() { try { return JSON.parse(localStorage.getItem('hr_cart') || '[]'); } catch { return []; } },
  set(items) { localStorage.setItem('hr_cart', JSON.stringify(items)); renderCartPill(); },
  add(id) { const c = Cart.get(); c.push(id); Cart.set(c); },
  clear() { Cart.set([]); },
};

function renderCartPill() {
  const el = document.getElementById('cart-count');
  if (el) el.textContent = String(Cart.get().length);
}

function money(n) { return '$' + n.toFixed(2); }

function addToCart(id) {
  Cart.add(id);
  const t = document.getElementById('toast');
  if (t) { t.textContent = 'Added to cart.'; t.style.display = 'block'; }
}

document.addEventListener('DOMContentLoaded', renderCartPill);
