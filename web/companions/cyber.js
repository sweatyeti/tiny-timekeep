/* Parked 2026-09-27: the retired Cyber cyborg avatar (renderCyberAvatar), an eye/face/jaw
 * cyborg. The Cyber theme is now painted by the supplied Hooded Netrunner
 * (web/companions/hooded-netrunner.js, styled by web/companions/hooded-netrunner.css),
 * which replaced the Neon Robot on 2026-09-30.
 * web/index.html no longer loads this file, so renderCyberAvatar is unreachable.
 * Kept in the repository for reference; the cyber mapping in
 * web/companions/registry.js now points to 'hooded-netrunner' and the
 * `cyber: renderCyberAvatar` entry is commented out.
 * Cyber cyborg avatar markup. Keep the structure here and its appearance in cyber.css.
 * Maintainer: do not load this file again without restoring the registry mapping and
 * removing this note.
 */
function renderCyberAvatar() {
  return '<div class="companion-cyber">' +
    '<span class="companion-cyber-hair"></span>' +
    '<span class="companion-cyber-face">' +
      '<span class="companion-cyber-eye companion-cyber-eye-natural"></span>' +
      '<span class="companion-cyber-eye companion-cyber-eye-lens"></span>' +
    '</span>' +
    '<span class="companion-cyber-jaw"></span>' +
  '</div>';
}
