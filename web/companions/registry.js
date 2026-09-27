/*
 * Companion registry: extend COMPANION_AVATARS with an avatar renderer, add
 * its theme(s) to COMPANION_REGISTRY, and load its script and CSS in index.html.
 * Unknown themes deliberately render no avatar while preserving the shared cue.
 *
 * The original Cute cat artwork (renderCatAvatar in companions/cat.js plus
 * companions/cat.css) is parked: its files are kept for reference, its script
 * and stylesheet are no longer loaded by index.html, and therefore the old
 * cat: renderCatAvatar, entry is commented out below the explanation rather
 * than left dangling.
 *
 * The original Cyber cyborg renderer (renderCyberAvatar in companions/cyber.js
 * plus companions/cyber.css) is parked exactly like the old cat: its files are
 * kept in the repository for reference, its script and stylesheet are no longer
 * loaded by index.html, and its entry below is commented out with an explanation
 * rather than left dangling.
 *
 * The original Poolside sun avatar (renderSunAvatar in companions/sun.js plus
 * companions/sun.css) is parked exactly like the old cat and cyber: its files
 * are kept in the repository for reference, its script and stylesheet are no
 * longer loaded by index.html, and its entry below is commented out with an
 * explanation rather than left dangling.
 */
const COMPANION_AVATARS = {
  // The original Cute cat artwork is parked (see top comment).
  // cat: renderCatAvatar,
  'cozy-cat': renderCozyCat,
  'neon-robot': renderNeonRobot,
  // The original Cyber cyborg renderer is parked (see top comment).
  // cyber: renderCyberAvatar,
  'poolside-turtle': renderPoolsideTurtle,
  // The original Poolside sun avatar is parked (see top comment).
  // sun: renderSunAvatar,
};

const COMPANION_REGISTRY = {
  cute: 'cozy-cat',
  cyber: 'neon-robot',
  poolside: 'poolside-turtle'
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
