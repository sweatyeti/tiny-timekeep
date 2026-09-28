/*
 * Poolside sun avatar markup. Keep the structure here and its appearance in sun.css.
 *
 * PARKED: This renderer (renderSunAvatar) is the retired Poolside sun avatar.
 * The file is kept in the repository for reference and is no longer loaded by
 * index.html. The Poolside theme is now rendered by the supplied Poolside Turtle
 * (companions/poolside-turtle.js, which defines renderPoolsideTurtle).
 *
 * Maintainer: do not load this file again without restoring the registry mapping
 * and removing this note.
 */
function renderSunAvatar() {
  return '<div class="companion-sun">' +
    '<span class="companion-sun-ray companion-sun-ray-top"></span>' +
    '<span class="companion-sun-ray companion-sun-ray-bottom"></span>' +
    '<span class="companion-sun-ray companion-sun-ray-left"></span>' +
    '<span class="companion-sun-ray companion-sun-ray-right"></span>' +
    '<span class="companion-sun-ray companion-sun-ray-tl"></span>' +
    '<span class="companion-sun-ray companion-sun-ray-tr"></span>' +
    '<span class="companion-sun-ray companion-sun-ray-bl"></span>' +
    '<span class="companion-sun-ray companion-sun-ray-br"></span>' +
    '<span class="companion-sun-face">' +
      '<span class="companion-sun-eye companion-sun-eye-left"></span>' +
      '<span class="companion-sun-eye companion-sun-eye-right"></span>' +
    '</span>' +
  '</div>';
}
