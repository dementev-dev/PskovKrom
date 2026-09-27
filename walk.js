// Пешеход: столкновения и пол для пешего режима (three-mesh-bvh, BVH строится лениво при первом подходе).
// Тело — капсула радиусом RADIUS_M от STEP_M над ногами до макушки: что ниже STEP_M (бордюр, ступень),
// перешагивается, остальное выталкивает по горизонтали — вдоль стены скользишь. Пол — луч вниз от колена:
// самая высокая поверхность рельефа, дорог, мостов, лестниц и зданий. Вода глубже WATER_DEPTH_M не пускает.
// Оси, как в app.js: x — север, y — вверх, z — восток, метры.
import * as THREE from 'three';
import { MeshBVH } from 'three-mesh-bvh';

export const EYE_M = 1.7;          // глаз над ногами
export const STEP_M = 0.45;        // выше этого не перешагнуть
export const RADIUS_M = 0.35;      // радиус тела: и ближняя плоскость камеры (0,25 м) не залезает в стену
const HEAD_M = 1.85;               // макушка
const WATER_DEPTH_M = 0.3;         // глубже — в воду не зайти
const SUBSTEP_M = 0.1;             // шаг проверки: меньше радиуса, сквозь тонкое не проскочить
const CELL_M = 32;                 // сетка поиска соседей
const BIG_M = 512;                 // что шире — проверяется всегда (стены, город, вода одним мешем)

const _v = new THREE.Vector3(), _tp = new THREE.Vector3(), _cp = new THREE.Vector3(), _tpw = new THREE.Vector3(),
  _cpw = new THREE.Vector3(), _push = new THREE.Vector3(), _lpush = new THREE.Vector3(), _hit = new THREE.Vector3();
const _seg = new THREE.Line3(), _lseg = new THREE.Line3(), _lbox = new THREE.Box3(), _ray = new THREE.Ray(),
  _lray = new THREE.Ray();

export class Walker {
  constructor() {
    this.entries = [];
    this.big = [];
    this.grid = new Map();
    this.stamp = 0;
    this.bvhMs = 0;           // сколько ушло на построение BVH (лениво, по мере подхода)
    this.bvhCount = 0;
    this.bvhMaxMs = 0;        // самое долгое построение (рывок при первом подходе)
    this.pos = new THREE.Vector3();   // ноги
    this.inWater = false;
    this.noclip = false;
    this.half = Infinity;     // полуразмер рельефа, м (scene.json half_m)
  }

  // role: 'solid' — не пройти и можно встать сверху; 'floor' — только пол (рельеф, дороги); 'water' — вода.
  // deck — по верху можно ходить и там можно появиться (мосты, лестницы, настилы).
  add(mesh, role, deck = false) {
    const geo = mesh.geometry;
    if (!geo?.attributes?.position) return;
    mesh.updateWorldMatrix(true, false);
    if (!geo.boundingBox) geo.computeBoundingBox();
    const m = mesh.matrixWorld.clone();
    const inv = m.clone().invert();
    const box = geo.boundingBox.clone().applyMatrix4(m);
    const s = new THREE.Vector3().setFromMatrixScale(m);
    const e = { mesh, geo, role, deck, m, inv, invLin: new THREE.Matrix3().setFromMatrix4(inv), box,
      invScale: 1 / Math.min(s.x, s.y, s.z), mark: 0 };
    this.entries.push(e);
    if (box.max.x - box.min.x > BIG_M || box.max.z - box.min.z > BIG_M) { this.big.push(e); return; }
    for (let i = Math.floor(box.min.x / CELL_M); i <= Math.floor(box.max.x / CELL_M); i++) {
      for (let j = Math.floor(box.min.z / CELL_M); j <= Math.floor(box.max.z / CELL_M); j++) {
        const k = `${i},${j}`;
        let c = this.grid.get(k);
        if (!c) this.grid.set(k, (c = []));
        c.push(e);
      }
    }
  }

  bvh(e) {
    if (!e.geo.boundsTree) {
      const t = performance.now();
      e.geo.boundsTree = new MeshBVH(e.geo, { targetLeafSize: 10 });
      const ms = performance.now() - t;
      this.bvhMs += ms;
      this.bvhMaxMs = Math.max(this.bvhMaxMs, ms);
      this.bvhCount++;
    }
    return e.geo.boundsTree;
  }

  // меши, чья рамка задевает квадрат (x ± r, z ± r) и отрезок высот [y0, y1]
  near(x, z, r, y0, y1, out) {
    out.length = 0;
    const st = ++this.stamp;
    const take = (e) => {
      if (e.mark === st) return;
      e.mark = st;
      const b = e.box;
      if (b.max.x < x - r || b.min.x > x + r || b.max.z < z - r || b.min.z > z + r) return;
      if (b.max.y < y0 || b.min.y > y1) return;
      out.push(e);
    };
    for (const e of this.big) take(e);
    for (let i = Math.floor((x - r) / CELL_M); i <= Math.floor((x + r) / CELL_M); i++) {
      for (let j = Math.floor((z - r) / CELL_M); j <= Math.floor((z + r) / CELL_M); j++) {
        const c = this.grid.get(`${i},${j}`);
        if (c) for (const e of c) take(e);
      }
    }
    return out;
  }

  // капсула в (x, feet, z) выталкивается из твёрдых мешей по горизонтали; возвращает сдвиг в out (x, z)
  pushOut(x, feet, z, out) {
    _seg.start.set(x, feet + STEP_M + RADIUS_M, z);
    _seg.end.set(x, feet + HEAD_M - RADIUS_M, z);
    const cand = this.near(x, z, RADIUS_M + 0.05, feet + STEP_M, feet + HEAD_M, this._c1 || (this._c1 = []));
    for (let pass = 0; pass < 2; pass++) {
      for (const e of cand) {
        if (e.role !== 'solid') continue;
        const bvh = this.bvh(e);
        _lseg.copy(_seg).applyMatrix4(e.inv);
        _lbox.makeEmpty().expandByPoint(_lseg.start).expandByPoint(_lseg.end).expandByScalar(RADIUS_M * e.invScale);
        bvh.shapecast({
          intersectsBounds: (b) => b.intersectsBox(_lbox),
          intersectsTriangle: (tri) => {
            tri.closestPointToSegment(_lseg, _tp, _cp);
            _tpw.copy(_tp).applyMatrix4(e.m);
            _cpw.copy(_cp).applyMatrix4(e.m);
            const d = _tpw.distanceTo(_cpw);
            if (d >= RADIUS_M || d < 1e-6) return false;
            _push.subVectors(_cpw, _tpw).multiplyScalar((RADIUS_M - d) / d);
            _push.y = 0;                                  // только по горизонтали: высоту решает пол
            _seg.start.add(_push); _seg.end.add(_push);
            _lpush.copy(_push).applyMatrix3(e.invLin);
            _lseg.start.add(_lpush); _lseg.end.add(_lpush);
            return false;
          },
        });
      }
    }
    out.x = _seg.start.x; out.z = _seg.start.z;
    return out;
  }

  // пол под (x, z): самая высокая поверхность ниже fromY. { y, e — чей пол, water — уровень воды или null }
  floorAt(x, z, fromY, depth = 60) {
    const cand = this.near(x, z, 0.01, fromY - depth, fromY, this._c2 || (this._c2 = []));
    _ray.origin.set(x, fromY, z);
    _ray.direction.set(0, -1, 0);
    let y = -Infinity, top = null, water = null;
    for (const e of cand) {
      const bvh = this.bvh(e);
      _lray.copy(_ray).applyMatrix4(e.inv);
      const h = bvh.raycastFirst(_lray, THREE.DoubleSide);
      if (!h) continue;
      _hit.copy(h.point).applyMatrix4(e.m);
      if (_hit.y < fromY - depth) continue;
      if (e.role === 'water') { water = Math.max(water ?? -Infinity, _hit.y); continue; }
      if (_hit.y > y) { y = _hit.y; top = e; }
    }
    if (!top) return null;
    return { y, e: top, water, wet: water != null && water > y + WATER_DEPTH_M };
  }

  // встать в (x, z): свободное место на земле или настиле — поиск по кольцам до 400 м (над рекой, над крышей),
  // за краем рельефа (half — полуразмер Landscape) — сначала к краю; true — нашлось
  spawn(x, z) {
    const out = { x: 0, z: 0 };
    const h = this.half - 2;
    x = THREE.MathUtils.clamp(x, -h, h);
    z = THREE.MathUtils.clamp(z, -h, h);
    for (let r = 0; r <= 400; r += Math.max(2, r * 0.15)) {
      const n = r === 0 ? 1 : THREE.MathUtils.clamp(Math.round((2 * Math.PI * r) / 3), 8, 48);
      for (let i = 0; i < n; i++) {
        const a = (i / n) * 2 * Math.PI;
        const px = x + r * Math.cos(a), pz = z + r * Math.sin(a);
        const f = this.floorAt(px, pz, 400, 800);
        if (!f || f.wet || (f.e.role === 'solid' && !f.e.deck)) continue;
        this.pushOut(px, f.y, pz, out);
        if (Math.hypot(out.x - px, out.z - pz) > 0.01) continue;
        this.pos.set(px, f.y, pz);
        this.inWater = false;
        return true;
      }
    }
    const f = this.floorAt(x, z, 400, 800);   // места нет — встаём как есть
    this.pos.set(x, f ? Math.max(f.y, f.water ?? -Infinity) : 0, z);
    this.inWater = !!f?.wet;
    return false;
  }

  // один подшаг по горизонтали; false — не пустило
  tryStep(dx, dz) {
    const p = this.pos;
    let x = p.x + dx, z = p.z + dz;
    if (!this.noclip) {
      const o = this.pushOut(x, p.y, z, this._o || (this._o = { x: 0, z: 0 }));
      x = o.x; z = o.z;
    }
    const f = this.floorAt(x, z, p.y + STEP_M);
    if (!f) return false;                                   // край рельефа
    if (this.noclip) {                                      // сквозь стены: по земле и по воде
      p.set(x, Math.max(f.y, f.water ?? -Infinity), z);
      return true;
    }
    if (f.wet) {
      if (!this.inWater) return false;                      // в воду не заходим
      p.set(x, Math.max(f.y, f.water), z);                  // уже в воде (появились там) — идём к берегу по воде
      return true;
    }
    this.inWater = false;
    p.set(x, f.y, z);
    return true;
  }

  // сдвиг на (dx, dz) с подшагами; упёрлись — пробуем по осям (скольжение вдоль берега и уступа)
  move(dx, dz) {
    const len = Math.hypot(dx, dz);
    if (len < 1e-6) return;
    const n = Math.ceil(len / SUBSTEP_M);
    const sx = dx / n, sz = dz / n;
    for (let i = 0; i < n; i++) {
      if (this.tryStep(sx, sz)) continue;
      if (Math.abs(sx) > 1e-6 && this.tryStep(sx, 0)) continue;
      if (Math.abs(sz) > 1e-6 && this.tryStep(0, sz)) continue;
      break;
    }
  }
}
