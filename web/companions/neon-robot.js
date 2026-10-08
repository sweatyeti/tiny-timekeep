/* Parked 2026-09-30: the retired Neon Robot artwork (renderNeonRobot), a cyan-screened robot
 * with magenta arms and a floating drone. The Cyber theme is now painted by the supplied
 * Hooded Netrunner (web/companions/hooded-netrunner.js, styled by
 * web/companions/hooded-netrunner.css).
 * web/index.html no longer loads this file, so renderNeonRobot is unreachable.
 * Kept in the repository for reference; the cyber mapping in
 * web/companions/registry.js now points to 'hooded-netrunner' and the
 * `'neon-robot': renderNeonRobot` entry is commented out.
 * Neon Robot avatar markup. Keep the structure here and its appearance in neon-robot.css.
 * Maintainer: do not load this file again without restoring the registry mapping and
 * removing this note.
 */
function renderNeonRobot() {
  return "<div class=\"companion-neon-robot\"><svg class=\"neon-robot-art\" viewBox=\"0 0 88 68\" width=\"88\" height=\"68\" xmlns=\"http://www.w3.org/2000/svg\" shape-rendering=\"crispEdges\" aria-hidden=\"true\"><g fill=\"#00FFFF\"><path d=\"M7 12h3v3H7zm68 5h3v3h-3zM17 5h3v3h-3z\"/><path d=\"M17 53h53v2H17z\" opacity=\".5\"/></g><path d=\"M40 8h8v7h-8z\" fill=\"#00FF41\"/><path d=\"M43 4h2v5h-2\" fill=\"#E8E8FF\"/><rect x=\"24\" y=\"16\" width=\"42\" height=\"34\" rx=\"6\" fill=\"#00FFFF\"/><rect x=\"27\" y=\"19\" width=\"36\" height=\"28\" rx=\"3\" fill=\"#0D1B2A\"/><path d=\"M19 26h5v14h-5zm47 0h5v14h-5z\" fill=\"#FF00FF\"/><path d=\"M30 51h9v8h-9zm21 0h9v8h-9z\" fill=\"#E8E8FF\"/><path d=\"M27 62h36v2H27z\" fill=\"#00FFFF\"/><g class=\"neon-robot-awake\" fill=\"#00FF41\"><path d=\"M34 29h7v5h-7zm15 0h7v5h-7z\"/><path d=\"M37 38h16v2H37zm3 2h10v2H40z\"/></g><g class=\"neon-robot-sleep\" fill=\"#00FF41\"><path d=\"M34 33h8v2h-8zm15 0h8v2h-8z\"/><path d=\"M41 40h9v2h-9z\"/></g><path d=\"M76 45h9v2h-9zm1 14h7v2h-7zm1-12 5 6-5 6m5-12-5 6 5 6\" fill=\"none\" stroke=\"#FF00FF\" stroke-width=\"2\"/><path d=\"M79 49h3v3h-3zm-1 7h5v2h-5z\" fill=\"#00FF41\"/></svg></div>";
}
