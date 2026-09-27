// PARKED 2026-09-27: the original Cute cat artwork. The Cute theme now renders the supplied
// Cozy Cat (`renderCozyCat` in companions/cozy-cat.js, styled by companions/cozy-cat.css), and
// index.html no longer loads this file, so `renderCatAvatar` is unreachable. Kept for reference;
// its `cat: renderCatAvatar` registry entry is commented out in companions/registry.js.
/* Cute cat avatar markup. Keep the structure here and its appearance in cat.css. */
function renderCatAvatar() {
  return '<div class="companion-cat">' +
    '<span class="companion-ear companion-ear-left"></span>' +
    '<span class="companion-ear companion-ear-right"></span>' +
    '<span class="companion-face">' +
      '<span class="companion-eye companion-eye-left"></span>' +
      '<span class="companion-eye companion-eye-right"></span>' +
    '</span>' +
    '<span class="companion-body"></span>' +
  '</div>';
}
