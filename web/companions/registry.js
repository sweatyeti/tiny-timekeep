/*
 * Companion registry: extend COMPANION_AVATARS with an avatar renderer, add
 * its theme(s) to COMPANION_REGISTRY, and load its script and CSS in index.html.
 * Unknown themes deliberately render no avatar while preserving the shared cue.
 */
const COMPANION_AVATARS = {
  // The original Cute cat artwork (renderCatAvatar in companions/cat.js plus
  // companions/cat.css) is parked: its files are kept for reference, its script
  // and stylesheet are no longer loaded by index.html, and therefore the old
  // cat: renderCatAvatar, entry is commented out below the explanation rather
  // than left dangling.
  // cat: renderCatAvatar,
  'cozy-cat': renderCozyCat,
  cyber: renderCyberAvatar,
  sun: renderSunAvatar
};

const COMPANION_REGISTRY = {
  cute: 'cozy-cat',
  cyber: 'cyber',
  poolside: 'sun'
};

function resolveCompanionAvatar(theme) {
  if (!theme || !Object.prototype.hasOwnProperty.call(COMPANION_REGISTRY, theme)) {
    return null;
  }
  const avatar = COMPANION_REGISTRY[theme];
  return Object.prototype.hasOwnProperty.call(COMPANION_AVATARS, avatar) ? avatar : null;
}

function renderCompanionScene(theme) {
  const scene = document.querySelector('.companion-scene');
  if (!scene) return;
  const avatar = resolveCompanionAvatar(theme);
  _companionCurrentAvatar = avatar;
  const renderAvatar = avatar && COMPANION_AVATARS[avatar];
  scene.innerHTML = (renderAvatar ? renderAvatar() : '') +
    '<span class="companion-sleep-cue"></span>';
}
