/*
 * Companion registry: extend COMPANION_AVATARS with an avatar renderer, add
 * its theme(s) to COMPANION_REGISTRY, and load its script and CSS in index.html.
 * Unknown themes deliberately render no avatar while preserving the shared cue.
 */
const COMPANION_AVATARS = {
  cat: renderCatAvatar,
  cyber: renderCyberAvatar,
  sun: renderSunAvatar
};

const COMPANION_REGISTRY = {
  cute: 'cat',
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
