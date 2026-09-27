// Псковский Кром — просмотрщик сцены build/web (scripts/web_export.py), three.js без сборки.
// Оси: x — север, y — вверх, z — восток, метры (план (X, Y, Z) → (X, Z, Y)).
// Параметры адреса: ?view=<имя> — точка обзора, &mode=walk — пешком, &shot=1 — без интерфейса (для снимков),
// &shadows=0 — без теней, &dpr=1 — плотность пикселей. Столкновения пешком — walk.js.
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { MeshoptDecoder } from 'three/addons/libs/meshopt_decoder.module.js';
import { Sky } from 'three/addons/objects/Sky.js';
import { Walker, EYE_M } from './walk.js';

const P = new URLSearchParams(location.search);
const $ = (id) => document.getElementById(id);
const WALK_MS = 1.6, RUN_MS = 5.0;
const SHADOW_HALF = 160;      // полуразмер области теней вокруг камеры, м
const K = window.__krom = { ready: false, loadMs: 0, fps: 0, frames: 0, errors: [] };
window.addEventListener('error', (e) => K.errors.push(String(e.message)));

if (P.get('shot') === '1') document.body.classList.add('shot');

// ---------- рендерер, сцена, небо, свет ----------
const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance',
  preserveDrawingBuffer: P.get('shot') === '1' });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, Number(P.get('dpr')) || 1.5));
renderer.setSize(innerWidth, innerHeight);
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 0.5;
renderer.shadowMap.enabled = P.get('shadows') !== '0';
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
document.body.appendChild(renderer.domElement);

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(45, innerWidth / innerHeight, 0.25, 45000);
camera.rotation.order = 'YXZ';

const S = await (await fetch('scene.json')).json();
const sunDir = new THREE.Vector3(...S.sun.dir).normalize();

const sky = new Sky();
sky.scale.setScalar(40000);
const su = sky.material.uniforms;
su.turbidity.value = 2.6; su.rayleigh.value = 2.0; su.mieCoefficient.value = 0.004; su.mieDirectionalG.value = 0.8;
su.sunPosition.value.copy(sunDir);
scene.add(sky);

// отражения и рассеянный свет неба — PMREM того же неба
{
  const pmrem = new THREE.PMREMGenerator(renderer);
  const envScene = new THREE.Scene();
  const s2 = new Sky();
  s2.scale.setScalar(50);
  Object.assign(s2.material.uniforms, THREE.UniformsUtils.clone(sky.material.uniforms));
  s2.material.uniforms.sunPosition.value.copy(sunDir);
  envScene.add(s2);
  scene.environment = pmrem.fromScene(envScene, 0, 0.1, 200).texture;
  scene.environmentIntensity = 0.9;
}
const fogColor = new THREE.Color().setRGB(0.52, 0.60, 0.70);   // дымка у горизонта (linear), подобрано по небу
scene.fog = new THREE.FogExp2(fogColor, 0.00009);

const sun = new THREE.DirectionalLight(0xfff2e0, 2.6);
sun.castShadow = true;
sun.shadow.mapSize.set(4096, 4096);
Object.assign(sun.shadow.camera, { left: -SHADOW_HALF, right: SHADOW_HALF, top: SHADOW_HALF, bottom: -SHADOW_HALF,
  near: 1, far: 3000 });
sun.shadow.bias = -0.0003;
sun.shadow.normalBias = 0.04;
scene.add(sun, sun.target);
scene.add(new THREE.HemisphereLight(0xcfe0ff, 0x4a4436, 0.35));

// ---------- загрузка ----------
const loader = new GLTFLoader().setMeshoptDecoder(MeshoptDecoder);
const texLoader = new THREE.TextureLoader();
const sizes = S.sizes || {};
const files = [...S.layers.map((l) => l.glb), ...S.models.map((m) => m.glb), S.trees];
const totalBytes = files.reduce((a, f) => a + (sizes[f] || 1e5), 0);
const got = {};
let done = 0;
const t0 = performance.now();
function progress(file, bytes) {
  got[file] = bytes;
  const b = Object.values(got).reduce((a, v) => a + v, 0);
  $('bar').firstChild.style.width = `${Math.min(100, (100 * b) / totalBytes).toFixed(1)}%`;
  $('loadtext').textContent = `${done} из ${files.length} файлов · ${(b / 1e6).toFixed(1)} из ${(totalBytes / 1e6).toFixed(1)} МБ`;
}
async function glb(file) {
  const g = await loader.loadAsync(file, (e) => progress(file, e.loaded));
  done++; progress(file, sizes[file] || 0);
  return g;
}

// детальные текстуры (Poly Haven 1K): цвет материала = палитра / среднее текстуры — в среднем цвет палитры
const tex = {};
for (const [k, t] of Object.entries(S.textures || {})) {
  const x = texLoader.load(t.file);
  x.colorSpace = THREE.SRGBColorSpace;
  x.wrapS = x.wrapT = THREE.RepeatWrapping;
  x.anisotropy = 8;
  tex[k] = { map: x, mean: t.mean, tile: t.tile_m };
}
const MAT_TEX = { stone: 'stone', wall: 'plaster', house: 'plaster', wood: 'planks' };
const touched = new WeakSet();
function dressMaterial(m) {
  if (!m || touched.has(m)) return;
  touched.add(m);
  const t = tex[MAT_TEX[m.name]];
  if (t && m.map == null) {
    const map = t.map.clone();
    map.repeat.set(1 / t.tile, 1 / t.tile);
    map.needsUpdate = true;
    m.map = map;
    m.color.setRGB(m.color.r / t.mean[0], m.color.g / t.mean[1], m.color.b / t.mean[2]);
  }
  if (m.name === 'glow') m.emissiveIntensity = 0.6;
  m.envMapIntensity = m.metalness > 0.5 ? 1.0 : 0.8;
}

// земля: мелкая текстура травы вблизи (яркость, не цвет) поверх запечённой 2K-текстуры
function groundDetail(m, t, near = 40, far = 220) {
  if (!t) return;
  m.onBeforeCompile = (sh) => {
    sh.uniforms.detailMap = { value: t.map };
    sh.uniforms.detailMean = { value: (t.mean[0] + t.mean[1] + t.mean[2]) / 3 };
    sh.uniforms.detailTile = { value: t.tile };
    sh.vertexShader = sh.vertexShader
      .replace('#include <common>', '#include <common>\nvarying vec3 vWPos;')
      .replace('#include <worldpos_vertex>', '#include <worldpos_vertex>\nvWPos = (modelMatrix * vec4(transformed, 1.0)).xyz;');
    sh.fragmentShader = sh.fragmentShader
      .replace('#include <common>', '#include <common>\nvarying vec3 vWPos;\nuniform sampler2D detailMap;\nuniform float detailMean;\nuniform float detailTile;')
      .replace('#include <map_fragment>', `#include <map_fragment>
        float dd = length(vWPos - cameraPosition);
        float fade = 1.0 - smoothstep(${near.toFixed(1)}, ${far.toFixed(1)}, dd);
        float l1 = dot(texture2D(detailMap, vWPos.xz / detailTile).rgb, vec3(0.3333)) / detailMean;
        float l2 = dot(texture2D(detailMap, vWPos.xz / (detailTile * 6.7) + 0.37).rgb, vec3(0.3333)) / detailMean;
        diffuseColor.rgb *= mix(1.0, l1, 0.75 * fade) * mix(1.0, l2, 0.3);`);
  };
}

const terrainMeshes = [];
const walker = new Walker();
walker.half = S.half_m;
// что участвует в пешем режиме: solid — не пройти и можно встать сверху, floor — пол, water — вода
const COLLIDE = { terrain: 'floor', roads: 'floor', water: 'water', walls: 'solid', bridges: 'solid', city: 'solid' };
const DECK = /FinPark_(Stairs|FlatBridge|HumpBridge)/;   // по этим героям ходят и на них можно появиться
async function loadLayer(l) {
  const g = await glb(l.glb);
  g.scene.traverse((o) => {
    if (!o.isMesh) return;
    const m = o.material;
    const role = COLLIDE[l.name];
    if (role) walker.add(o, role, l.name === 'bridges');
    if (l.name === 'terrain') {
      terrainMeshes.push(o);
      o.receiveShadow = true;
      m.roughness = 0.95;
      groundDetail(m, tex.grass);
    } else if (l.name === 'horizon') {
      m.roughness = 1;
    } else if (l.name === 'water') {
      m.roughness = 0.05; m.metalness = 0.0; m.envMapIntensity = 1.2;
    } else if (l.name === 'roads') {
      o.receiveShadow = true;
      m.polygonOffset = true; m.polygonOffsetFactor = -2; m.polygonOffsetUnits = -4;
      groundDetail(m, m.name === 'road_asphalt' ? tex.asphalt : (m.name === 'road_cobble' ? tex.cobble : null), 30, 150);
    } else {
      o.castShadow = true; o.receiveShadow = true;
      dressMaterial(m);
    }
  });
  scene.add(g.scene);
}

const _m = new THREE.Matrix4(), _q = new THREE.Quaternion(), _e = new THREE.Euler(), _p = new THREE.Vector3(),
  _s = new THREE.Vector3();
function itemMatrix(it) {
  _e.set(0, it[3], 0);
  _q.setFromEuler(_e);
  return new THREE.Matrix4().compose(_p.set(it[0], it[1], it[2]), _q, _s.set(it[4], it[5], it[6]));
}
async function loadModel(md) {
  const g = await glb(md.glb);
  g.scene.updateMatrixWorld(true);
  const big = md.kind === 'hero' || md.triangles > 3000;
  if (md.items.length === 1 || md.kind === 'hero') {
    md.items.forEach((it, i) => {
      const o = i === 0 ? g.scene : g.scene.clone();
      o.applyMatrix4(itemMatrix(it));
      if (md.names) o.name = md.names[i];
      o.traverse((c) => { if (c.isMesh) { c.castShadow = true; c.receiveShadow = true; dressMaterial(c.material); } });
      scene.add(o);
      o.updateMatrixWorld(true);
      o.traverse((c) => { if (c.isMesh) walker.add(c, 'solid', DECK.test(md.glb)); });
    });
    return;
  }
  // много одинаковых — InstancedMesh на каждый примитив; матрица узла GLB (деквантование) — внутри матрицы экземпляра
  g.scene.traverse((c) => {
    if (!c.isMesh) return;
    dressMaterial(c.material);
    const im = new THREE.InstancedMesh(c.geometry, c.material, md.items.length);
    md.items.forEach((it, i) => im.setMatrixAt(i, _m.multiplyMatrices(itemMatrix(it), c.matrixWorld)));
    im.castShadow = big; im.receiveShadow = true;
    im.computeBoundingSphere();
    scene.add(im);
  });
}

// деревья: низкополигональные кроны и стволы, по экземпляру на точку build/trees/points.json
async function loadTrees() {
  const r = await fetch(S.trees);
  const T = await r.json();
  done++; progress(S.trees, sizes[S.trees] || 0);
  const tint = { birch: [1.3, 1.25, 0.85], linden: [1.0, 1.05, 0.85], maple: [0.95, 1.0, 0.8], poplar: [0.85, 1.0, 0.9],
    willow: [1.15, 1.2, 1.15], spruce: [0.5, 0.72, 0.7], conifer: [0.55, 0.75, 0.72], pine: [0.6, 0.8, 0.7] };
  const conif = new Set(['spruce', 'conifer', 'pine', 'fir']);
  const crownGeo = new THREE.IcosahedronGeometry(1, 1);
  { // неровная крона: сдвиг вершин (одна форма на все деревья, повороты разные)
    const a = crownGeo.attributes.position;
    for (let i = 0; i < a.count; i++) {
      const k = 1 + 0.18 * Math.sin(a.getX(i) * 5.1 + a.getZ(i) * 3.7) * Math.cos(a.getY(i) * 4.3);
      a.setXYZ(i, a.getX(i) * k, a.getY(i) * k, a.getZ(i) * k);
    }
    crownGeo.computeVertexNormals();
  }
  const coneGeo = new THREE.ConeGeometry(1, 1, 7, 1);
  coneGeo.translate(0, 0.5, 0);
  const trunkGeo = new THREE.CylinderGeometry(0.6, 1, 1, 5, 1, true);
  trunkGeo.translate(0, 0.5, 0);
  const leafMat = new THREE.MeshStandardMaterial({ roughness: 0.85, color: 0xffffff });
  const barkMat = new THREE.MeshStandardMaterial({ roughness: 0.9, color: new THREE.Color().setRGB(...T.bark) });
  const pts = T.points;
  const nCon = pts.filter((p) => conif.has(T.species[p[5]])).length;
  const crowns = new THREE.InstancedMesh(crownGeo, leafMat, pts.length - nCon);
  const cones = new THREE.InstancedMesh(coneGeo, leafMat, Math.max(1, nCon));
  const trunks = new THREE.InstancedMesh(trunkGeo, barkMat, pts.length);
  const base = new THREE.Color().setRGB(...T.foliage);
  const col = new THREE.Color();
  let ic = 0, io = 0, it = 0;
  const shrub = T.kinds.indexOf('shrub');
  let seed = 1;
  const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  for (const p of pts) {
    const [x, y, z, h, crown, sp, kind, yaw] = p;
    const name = T.species[sp];
    const t = tint[name] || [1, 1, 1];
    const v = 0.85 + 0.3 * rnd();
    col.setRGB(base.r * t[0] * v, base.g * t[1] * v, base.b * t[2] * v);
    _e.set(0, (-yaw * Math.PI) / 180, 0); _q.setFromEuler(_e);
    const r = Math.max(0.6, crown / 2);
    if (conif.has(name)) {
      cones.setMatrixAt(io, _m.compose(_p.set(x, y + h * 0.15, z), _q, _s.set(r, h * 0.85, r)));
      cones.setColorAt(io++, col);
    } else {
      const ch = kind === shrub ? h * 0.9 : Math.min(h * 0.72, Math.max(crown * 1.05, h * 0.5));
      crowns.setMatrixAt(ic, _m.compose(_p.set(x, y + h - ch / 2, z), _q, _s.set(r, ch / 2, r)));
      crowns.setColorAt(ic++, col);
    }
    const th = kind === shrub ? 0.01 : h * 0.55;
    const tr = Math.max(0.1, h * 0.016);
    trunks.setMatrixAt(it++, _m.compose(_p.set(x, y - 0.3, z), _q, _s.set(tr, th + 0.3, tr)));
  }
  for (const im of [crowns, cones, trunks]) {
    im.castShadow = true; im.receiveShadow = true;
    im.instanceMatrix.needsUpdate = true;
    if (im.instanceColor) im.instanceColor.needsUpdate = true;
    im.computeBoundingSphere();
    scene.add(im);
  }
  K.trees = pts.length;
}

// ---------- управление ----------
const cam = { yaw: 0, pitch: 0, speed: 40, mode: P.get('mode') === 'walk' ? 'walk' : 'fly', y: 0 };
const keys = new Set();
const ray = new THREE.Raycaster();
const DOWN = new THREE.Vector3(0, -1, 0);
function groundAt(x, z) {
  ray.set(_p.set(x, 500, z), DOWN);
  ray.far = 1000;
  const h = ray.intersectObjects(terrainMeshes, false)[0];
  return h ? h.point.y : null;
}
function lookAt(eye, target) {
  camera.position.set(...eye);
  const d = new THREE.Vector3(...target).sub(camera.position).normalize();
  cam.yaw = Math.atan2(-d.x, -d.z);
  cam.pitch = Math.asin(THREE.MathUtils.clamp(d.y, -0.9999, 0.9999));
}
function setView(name) {
  const v = S.views.find((q) => q.name === name) || S.views[0];
  lookAt(v.eye, v.target);
  $('views').value = v.name;
  const h = Math.abs(v.eye[1] - (groundAt(v.eye[0], v.eye[2]) ?? v.eye[1]));
  cam.speed = THREE.MathUtils.clamp(h * 0.4, 8, 250);
  if (cam.mode === 'walk') setMode('walk');
}
function setMode(m) {
  cam.mode = m;
  $('mode').textContent = m === 'walk' ? 'Полёт' : 'Пешком';
  if (m === 'walk') {   // на ближайшее свободное место на земле или настиле
    K.spawnOk = walker.spawn(camera.position.x, camera.position.z);
    camera.position.set(walker.pos.x, walker.pos.y + EYE_M, walker.pos.z);
  }
}
function setNoclip(on) {
  walker.noclip = on;
  $('noclip').textContent = `Сквозь стены: ${on ? 'вкл' : 'выкл'}`;
}
for (const v of S.views) {
  const o = document.createElement('option');
  o.value = v.name; o.textContent = v.label;
  $('views').appendChild(o);
}
$('views').onchange = (e) => { setView(e.target.value); e.target.blur(); };
$('mode').onclick = (e) => { setMode(cam.mode === 'walk' ? 'fly' : 'walk'); e.target.blur(); };
$('noclip').onclick = (e) => { setNoclip(!walker.noclip); e.target.blur(); };
$('shadows').onclick = (e) => {
  sun.castShadow = !sun.castShadow;
  e.target.textContent = `Тени: ${sun.castShadow ? 'вкл' : 'выкл'}`; e.target.blur();
};

const canvas = renderer.domElement;
let drag = false;
canvas.addEventListener('mousedown', () => { drag = true; });
addEventListener('mouseup', () => { drag = false; });
canvas.addEventListener('dblclick', () => canvas.requestPointerLock?.());
canvas.addEventListener('click', () => { if (!document.pointerLockElement) canvas.requestPointerLock?.()?.catch?.(() => {}); });
document.addEventListener('pointerlockchange', () => {
  $('cross').style.display = document.pointerLockElement === canvas ? 'block' : 'none';
});
addEventListener('mousemove', (e) => {
  if (document.pointerLockElement !== canvas && !drag) return;
  cam.yaw -= e.movementX * 0.0022;
  cam.pitch = THREE.MathUtils.clamp(cam.pitch - e.movementY * 0.0022, -1.55, 1.55);
});
addEventListener('wheel', (e) => { cam.speed = THREE.MathUtils.clamp(cam.speed * (e.deltaY > 0 ? 0.8 : 1.25), 2, 2000); });
// окна «Управление» и «Источники»: пока открыты, сцена клавиш не получает
let overlay = null;
function openOverlay(id) {
  closeOverlay();
  overlay = $(id);
  overlay.classList.add('open');
  keys.clear();
  if (document.pointerLockElement) document.exitPointerLock();
  if (id === 'credits') fillCredits();
}
function closeOverlay() {
  if (overlay) overlay.classList.remove('open');
  overlay = null;
}
for (const id of ['help', 'credits']) {
  $(id).addEventListener('click', (e) => { if (e.target === $(id) || e.target.classList.contains('close')) closeOverlay(); });
}
$('btn-help').onclick = (e) => { openOverlay('help'); e.target.blur(); };
$('btn-credits').onclick = (e) => { openOverlay('credits'); e.target.blur(); };
for (const v of S.views) {
  const b = document.createElement('button');
  b.textContent = v.label;
  b.onclick = () => { setView(v.name); closeOverlay(); };
  $('viewlist').appendChild(b);
}
const esc = (t) => String(t).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
let creditsLoaded = false;
async function fillCredits() {   // авторы фото и текстур — credits.json из web_export.py
  if (creditsLoaded) return;
  creditsLoaded = true;
  try {
    const C = await (await fetch('credits.json')).json();
    $('textures').innerHTML = C.textures.map((t) =>
      `<a href="${esc(t.url)}" target="_blank" rel="noopener">${esc(t.name)}</a> (${esc(t.authors.join(', '))})`).join(', ');
    $('photos-total').textContent = `${C.photos_total} фото`;
    $('photos').innerHTML = C.photos.map((g) => `<li><b>${esc(g.object)}</b> — ${g.photos}: ` +
      g.authors.map((a) => `${esc(a.name)}${a.n > 1 ? ` (${a.n})` : ''}, ${esc(a.licenses.join(', '))}`).join('; ') +
      '</li>').join('');
    $('credits-gen').textContent = `Список авторов собран из манифестов фото при экспорте сцены ${C.generated}.`;
  } catch (err) {
    creditsLoaded = false;
    $('photos').innerHTML = `<li>Не удалось загрузить credits.json: ${esc(err.message || err)}</li>`;
  }
}

addEventListener('keydown', (e) => {
  if (overlay) {
    if (e.code === 'Escape' || e.code === 'KeyH') closeOverlay();
    return;
  }
  if (e.target instanceof HTMLSelectElement) return;
  if (e.code === 'KeyH' || e.code === 'F1') { e.preventDefault(); openOverlay('help'); return; }
  keys.add(e.code);
  if (e.code === 'KeyN') setNoclip(!walker.noclip);
  if (e.code === 'KeyG') setMode(cam.mode === 'walk' ? 'fly' : 'walk');
  if (e.code === 'KeyV') {
    const i = (S.views.findIndex((q) => q.name === $('views').value) + 1) % S.views.length;
    setView(S.views[i].name);
  }
});
addEventListener('keyup', (e) => keys.delete(e.code));
addEventListener('blur', () => keys.clear());
addEventListener('resize', () => {
  camera.aspect = innerWidth / innerHeight; camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
});

const fwd = new THREE.Vector3(), right = new THREE.Vector3(), mv = new THREE.Vector3();
let moveAcc = 0, moveN = 0, moveMax = 0;
function move(dt) {
  const k = (c) => (keys.has(c) ? 1 : 0);
  const f = k('KeyW') + k('ArrowUp') - k('KeyS') - k('ArrowDown');
  const s = k('KeyD') + k('ArrowRight') - k('KeyA') - k('ArrowLeft');
  const u = k('KeyE') + k('Space') - k('KeyQ') - k('KeyC');
  const fast = keys.has('ShiftLeft') || keys.has('ShiftRight');
  right.set(Math.cos(cam.yaw), 0, -Math.sin(cam.yaw));
  if (cam.mode === 'walk') {
    fwd.set(-Math.sin(cam.yaw), 0, -Math.cos(cam.yaw));
    mv.copy(fwd).multiplyScalar(f).addScaledVector(right, s);
    if (mv.lengthSq() > 0) mv.normalize().multiplyScalar((fast ? RUN_MS : WALK_MS) * dt);
    const t = performance.now();
    walker.move(mv.x, mv.z);
    const ms = performance.now() - t;
    moveAcc += ms; moveN++; moveMax = Math.max(moveMax, ms);
    camera.position.x = walker.pos.x; camera.position.z = walker.pos.z;
    const target = walker.pos.y + EYE_M;   // по высоте — плавно: ступени и уступы без рывков
    camera.position.y += (target - camera.position.y) * Math.min(1, dt * 12);
  } else {
    fwd.set(-Math.sin(cam.yaw) * Math.cos(cam.pitch), Math.sin(cam.pitch), -Math.cos(cam.yaw) * Math.cos(cam.pitch));
    mv.copy(fwd).multiplyScalar(f).addScaledVector(right, s).addScaledVector(DOWN, -u);
    if (mv.lengthSq() > 0) camera.position.addScaledVector(mv.normalize(), cam.speed * (fast ? 4 : 1) * dt);
    if (mv.lengthSq() > 0) {
      const g = groundAt(camera.position.x, camera.position.z);
      if (g != null && camera.position.y < g + 0.8) camera.position.y = g + 0.8;
    }
  }
  camera.rotation.set(cam.pitch, cam.yaw, 0);
}

// тени — квадрат SHADOW_HALF вокруг точки перед камерой, шаг — по текселю (без мерцания)
const focus = new THREE.Vector3();
function placeSun() {
  fwd.set(-Math.sin(cam.yaw), 0, -Math.cos(cam.yaw));
  focus.copy(camera.position).addScaledVector(fwd, SHADOW_HALF * 0.6);
  const g = groundAt(focus.x, focus.z);
  focus.y = g ?? camera.position.y;
  const texel = (2 * SHADOW_HALF) / sun.shadow.mapSize.x;
  focus.x = Math.round(focus.x / texel) * texel; focus.z = Math.round(focus.z / texel) * texel;
  sun.target.position.copy(focus);
  sun.position.copy(focus).addScaledVector(sunDir, 1500);
}

// ---------- запуск ----------
try {
  await Promise.all([...S.layers.map(loadLayer), ...S.models.map(loadModel), loadTrees()]);
} catch (err) {
  $('loadtext').textContent = `Ошибка загрузки: ${err.message || err}`;
  K.errors.push(String(err.stack || err));
  throw err;
}
K.loadMs = Math.round(performance.now() - t0);
$('loading').style.display = 'none';
setView(P.get('view') || 'oblique');
if (cam.mode === 'walk') setMode('walk');

const clock = new THREE.Clock();
let acc = 0, frames = 0;
function frame() {
  const dt = Math.min(clock.getDelta(), 0.1);
  move(dt);
  placeSun();
  renderer.render(scene, camera);
  frames++; acc += dt; K.frames++;
  if (acc >= 0.5) {
    K.fps = Math.round(frames / acc);
    const i = renderer.info.render;
    const p = camera.position;
    $('stats').textContent =
      `FPS ${K.fps}   вызовов ${i.calls}   треуг. ${(i.triangles / 1e6).toFixed(2)} млн\n` +
      `режим ${cam.mode === 'walk' ? `пешком${walker.noclip ? ', сквозь стены' : ''}` : `полёт ${Math.round(cam.speed)} м/с`}   загрузка ${(K.loadMs / 1000).toFixed(1)} с\n` +
      `С ${p.x.toFixed(0)}  В ${p.z.toFixed(0)}  высота ${p.y.toFixed(1)} м`;
    K.calls = i.calls; K.triangles = i.triangles;
    if (moveN) { K.moveMs = moveAcc / moveN; K.moveMaxMs = moveMax; moveAcc = 0; moveN = 0; moveMax = 0; }
    K.bvhMs = Math.round(walker.bvhMs); K.bvhCount = walker.bvhCount;
    frames = 0; acc = 0;
  }
  requestAnimationFrame(frame);
}
K.setView = setView; K.setMode = setMode; K.setNoclip = setNoclip; K.walker = walker; K.keys = keys; K.camera = camera; K.cam = cam; K.renderer = renderer; K.scene = scene;
// замер: n кадров подряд с ожиданием GPU (readPixels) — мс на кадр без ограничения vsync
K.bench = (n = 60) => {
  const gl = renderer.getContext(), px = new Uint8Array(4);
  renderer.render(scene, camera); gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px);
  const t = performance.now();
  for (let i = 0; i < n; i++) { placeSun(); renderer.render(scene, camera); gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px); }
  return (performance.now() - t) / n;
};
K.ready = true;
requestAnimationFrame(frame);
