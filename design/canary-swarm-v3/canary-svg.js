/* Canary Swarm v3: flat cage, cute small canary. No em-dashes. */
(function (global) {
  "use strict";

  function cageDome(id) {
    return (
      '<svg class="cage-dome-svg" viewBox="0 0 400 180" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false">' +
      '<path fill="#FFFFFF" stroke="#C99A2E" stroke-width="2.6" d="M18 179 V90 A182 80 0 0 1 382 90 V179"/>' +
      '<line x1="18" y1="179" x2="382" y2="179" stroke="#C99A2E" stroke-width="2.6"/>' +
      '<line x1="200" y1="22" x2="200" y2="36" stroke="#C99A2E" stroke-width="2.2" stroke-linecap="round"/>' +
      '<circle cx="200" cy="14" r="8" fill="#FFFFFF" stroke="#C99A2E" stroke-width="2.4"/>' +
      "</svg>"
    );
  }

  function canary(id) {
    const p = "canary-" + id;
    return (
      '<svg class="canary-svg" viewBox="0 0 100 88" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false">' +
      '<g class="canary__figure">' +
      '<g class="canary__tail">' +
      '<path d="M22 48 C10 44 4 38 2 30 C12 38 18 44 28 50 Z" fill="#F5D018"/>' +
      '<path d="M22 54 C8 56 4 62 3 70 C14 62 20 56 30 52 Z" fill="#FACC15"/>' +
      "</g>" +
      '<g class="canary__body">' +
      '<ellipse cx="48" cy="52" rx="26" ry="20" fill="#FACC15"/>' +
      '<ellipse cx="52" cy="58" rx="16" ry="11" fill="#FDE68A"/>' +
      "</g>" +
      '<g class="canary__wing">' +
      '<ellipse cx="40" cy="54" rx="13" ry="8.5" fill="#F5D018" transform="rotate(-18 40 54)"/>' +
      "</g>" +
      '<g class="canary__head">' +
      '<circle cx="70" cy="34" r="15.5" fill="#FACC15"/>' +
      '<g class="canary__eye-live">' +
      '<circle cx="75" cy="32" r="4.1" fill="#161412"/>' +
      '<circle cx="76.4" cy="30.7" r="1.35" fill="#FFFFFF"/>' +
      '<ellipse class="canary__lid" cx="75" cy="32" rx="4.4" ry="4.4" fill="#FACC15"/>' +
      "</g>" +
      '<g class="canary__eye-dead" stroke="#161412" stroke-width="1.8" stroke-linecap="round" fill="none">' +
      '<path d="M71 28 L79 36 M79 28 L71 36"/>' +
      "</g>" +
      "</g>" +
      '<g class="canary__beak">' +
      '<path d="M84 33 L97 37 L84 41 Z" fill="#E8943A"/>' +
      "</g>" +
      '<g class="canary__legs" stroke="#9C6B3F" stroke-width="1.6" stroke-linecap="round" fill="none">' +
      '<path d="M42 70 L40 84 M34 84 L40 84 L45 86"/>' +
      '<path d="M56 70 L58 84 M53 86 L58 84 L64 84"/>' +
      "</g>" +
      "</g>" +
      "</svg>"
    );
  }

  function mark(id, opts) {
    const p = "mark-" + id;
    return (
      '<svg class="sp-mark-svg" viewBox="0 0 64 76" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Canary Swarm mark">' +
      '<line x1="32" y1="12" x2="32" y2="18" stroke="#C99A2E" stroke-width="2" stroke-linecap="round"/>' +
      '<circle cx="32" cy="8" r="5" fill="#FFFFFF" stroke="#C99A2E" stroke-width="2.2"/>' +
      '<path d="M8 72 V40 A24 24 0 0 1 56 40 V72" fill="none" stroke="#C99A2E" stroke-width="2.4"/>' +
      '<line x1="32" y1="18" x2="18" y2="48" stroke="#C99A2E" stroke-width="1.3" stroke-linecap="round"/>' +
      '<line x1="32" y1="18" x2="46" y2="48" stroke="#C99A2E" stroke-width="1.3" stroke-linecap="round"/>' +
      '<line x1="14" y1="48" x2="50" y2="48" stroke="#9C6B3F" stroke-width="2.2" stroke-linecap="round"/>' +
      '<g fill="#FACC15">' +
      '<ellipse cx="30" cy="42" rx="7.5" ry="5.6"/>' +
      '<circle cx="36" cy="38" r="4.2"/>' +
      '<path d="M40 38 L45 40 L40 42 Z" fill="#E8943A"/>' +
      "</g>" +
      '<circle cx="37.4" cy="37.2" r="1.05" fill="#161412"/>' +
      "</svg>"
    );
  }

  function renderInto(el, html) {
    if (!el) return;
    el.innerHTML = html;
  }

  function hydrate() {
    document.querySelectorAll("[data-sp-dome]").forEach(function (el) {
      renderInto(el, cageDome(el.getAttribute("data-sp-dome")));
    });
    document.querySelectorAll("[data-sp-canary]").forEach(function (el) {
      renderInto(el, canary(el.getAttribute("data-sp-canary")));
    });
    document.querySelectorAll("[data-sp-mark]").forEach(function (el) {
      var onDark = el.getAttribute("data-on-dark") !== "false";
      renderInto(el, mark(el.getAttribute("data-sp-mark"), { onDark: onDark }));
    });
  }

  global.CanarySwarmArt = { cageDome: cageDome, canary: canary, mark: mark, hydrate: hydrate };
})(typeof window !== "undefined" ? window : globalThis);
