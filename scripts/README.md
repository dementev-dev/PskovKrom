# scripts — скрипты проекта

Единственный список скриптов, их запуска и порядка сборки. Подробности каждого скрипта — в его докстринге (первые строки файла).

## Запуск

| Где | Команда |
|---|---|
| Редактор UE, скрипт | `python scripts/ue_run.py scripts/<x>.py` |
| Редактор UE, функция модуля | `python scripts/ue_run.py -c "import sys; sys.path.insert(0, 'D:/PskovKrom/scripts'); import importlib, <m>; importlib.reload(<m>); <m>.<f>(…)"` |
| Офлайн (numpy, rasterio…) | `.venv\Scripts\python scripts/<x>.py` |
| Планы и утилиты (чистый Python) | `python scripts/<x>.py` |
| Blender без окна | `python scripts/bl_run.py scripts/blender/<x>.py [-- аргументы]` |

- `ue_run` находит среди процессов проекта редактор (тот, у кого есть подсистемы редактора): команда уходит в него, даже когда рядом идёт рендер `UnrealEditor-Cmd -game`. Код возврата: 0 — скрипт отработал, 1 — ошибка в скрипте, 2 — редактор не найден.
- Строки лога скрипта (`[имя] …`) `ue_run` печатает в консоль. Работа на тиках редактора (`heights_krom`, `shot_krom`, `budget_krom`, `render_krom`) кончается позже команды — её итог смотреть в `Krom/Saved/Logs/Krom.log`.
- Через `-c` вызываются функции модулей (в таблице — «модуль»); остальные скрипты собирают сцену уже при импорте.
- Python редактора живёт между запусками: модули из `scripts/` кешируются, после правки — `importlib.reload(<m>)`.
- Кириллица и знаки «→», «≈» в консоли Windows — с `PYTHONIOENCODING=utf-8` (bash: префикс команды; PowerShell: `$env:PYTHONIOENCODING = "utf-8"`). Без него офлайн-скрипты падают на `print`, `ue_run` заменяет такие знаки на «?».

## Соглашения
- Акторы скрипта лежат в папке Outliner `Generated/<имя_скрипта>` (тег `generated:<имя_скрипта>` — AGENTS.md).
- Размеры в коде — метры; в uu (×100) переводит сам скрипт.
- API редактора — editor subsystems и `unreal.load_asset`: `EditorScriptingUtilities` в UE 5.8 deprecated (D-011).

## Первичная сборка (D-045)
В свежем клоне есть `L_Krom` с Landscape и 64 прокси (`__ExternalActors__` в git) и все `refs/`. Мешей, материалов, `SEQ_Flyover` и `build/` нет. Шаги — по порядку, шаг готов, когда выполнен его критерий. «Первая» — шаг нужен при первой сборке и при правке его собственных входов, от рельефа он не зависит.

1. **Окружение** (один раз):

       git lfs pull
       git config core.hooksPath .githooks
       python -m venv .venv
       .venv\Scripts\python -m pip install -r scripts/requirements.txt

   Blender — по AGENTS.md (или путь в переменной `BLENDER`). Для `web_export.py` нужен ещё node/npx.
   Готово: `.venv\Scripts\python -c "import rasterio"` без ошибки; `refs/dem/heightmap_L_Krom.png` открывается как картинка, а не как текстовый указатель LFS.
   Текстуры `refs/textures/` приходят из git; `textures_fetch`, `leaf_atlas`, `water_normals` запускать только при их правке.

2. **Офлайн** (`.venv`), по порядку. Готово: код возврата 0 и выходной файл со свежим временем.

   | Скрипт | Когда | Нужно до него | Выход |
   |---|---|---|---|
   | `terrain_krom` | каждая | — | `build/terrain/heightmap_L_Krom_rg.png`, `build/terrain/water_pools.json`, `refs/dem/*` |
   | `horizon_mesh` | первая | terrain_krom (стык по heightmap) | `build/horizon/horizon.json`, `*.bin`, `T_HorizonMask.png` |
   | `roads_mesh` | каждая | terrain_krom (heightmap) | `build/roads/roads.json` |
   | `trees_points` | каждая | terrain_krom (рельеф и маски) | `build/trees/points.json` |
   | `city_mesh` | каждая | terrain_krom (heightmap) | `build/city/city.json` |
   | `cemetery_points` | каждая | trees_points | `build/cemetery/points.json` |
   | `furniture_points` | первая | — (только OSM) | `build/furniture/points.json` |

3. **Blender**, после `terrain_krom`: `pskov_church` строит ограды храмов по heightmap. Каждый скрипт — отдельным запуском (bash):

       for s in cathedral belfry round_tower facet_tower paromenye chapels pskov_church krom_yard prikaz \
                pskovgu pozemskogo zapskovye lenina tree street_furniture cemetery landmarks finpark; do
         python scripts/bl_run.py scripts/blender/$s.py || echo "FAIL $s"; done

   Готово: ни одного `FAIL`; GLB героев лежат в `build/blender/` — `heroes_krom` импортирует всех героев плана и без любого из них остановится. Превью с камер фото строятся, только если в `build/` есть файлы восстановления камер (`views.json`, `solve.json`); выгрузке GLB они не нужны.

4. **Редактор.** Открыть `Krom\Krom.uproject`: `Content/Python/init_unreal.py` сам держит загруженным регион `LoadAll` (все 64 прокси Landscape). Дальше по порядку `python scripts/ue_run.py scripts/<x>.py`:

   | # | Скрипт | Когда | Почему здесь | Готово, когда в выводе |
   |---|---|---|---|---|
   | 1 | `level_krom` | первая | свет, небо, объём `LoadAll` | `[level_krom] /Game/Krom/Maps/L_Krom: …, saved` |
   | 2 | `heights_krom` | каждая | высоты Landscape из `build/terrain`; все прокси — `is_spatially_loaded=False`. Landscape в уровне нет — раздел «Landscape» | `[heights_krom] done` в `Krom.log`; следующий шаг — после этой строки |
   | 3 | `horizon_krom` | первая | `T_HorizonMask` нужна `landscape_krom` | `[horizon_krom] done` |
   | 4 | `materials_krom` | первая | `M_Krom<Ключ>`; `T_BuildingPlanks_D` нужна `landscape_krom` (настилы) | `[materials_krom] материалов …` |
   | 5 | `landscape_krom` | каждая | материал земли, вода; `T_Ground*_D` нужны `roads_krom` и `gabions_krom` | `[landscape_krom] done` |
   | 6 | `blockout_krom` | каждая | `M_Blockout` и `MI_BO_*` — материалы для ключей цвета без `M_Krom<Ключ>` | `[blockout_krom] done` |
   | 7 | `walls_krom` | каждая | убирает коробки стен blockout | `[walls_krom] done` |
   | 8 | `heroes_krom` | каждая | убирает примитивы blockout своих зданий | `[heroes_krom] done` |
   | 9 | `bridge_krom` | каждая | `M_KromConcrete`, `M_KromRailing` нужны `finpark_krom` | `[bridge_krom] done` |
   | 10 | `gabions_krom` | каждая | после `heights_krom` и `landscape_krom` | `[gabions_krom] done` |
   | 11 | `furniture_krom` | каждая | `SM_Furn_Bench`, `MI_KromLampGlow` нужны `finpark_krom` | `[furniture_krom] done` |
   | 12 | `finpark_krom` | каждая | после мостов и малых форм | `[finpark_krom] done` |
   | 13 | `trees_krom` | каждая | | `[trees_krom] done` |
   | 14 | `city_krom` | каждая | | `[city_krom] done` |
   | 15 | `roads_krom` | каждая | | `[roads_krom] done` |
   | 16 | `cemetery_krom` | каждая | `MI_BO_Ruin` от blockout | `[cemetery_krom] done` |
   | 17 | `landmarks_krom` | каждая | | `[landmarks_krom] done` |
   | 18 | `flyover_krom` | первая | `SEQ_Flyover` для `render_krom` | `[flyover_krom] /Game/Krom/Cinematics/SEQ_Flyover: …` |

5. **Проверка:** `view_krom.view('oblique')` → `media/renders/views/oblique.png`: земля и здания без «шашечки» материалов, без дыр в земле, стены и герои на местах.
6. По желанию: `cameras_krom` (ракурсы `CAM_*` и их снимки), `web_export.py` (веб-сцена, редактор не нужен).

## После правки рельефа
Самая частая пересборка: правки `terrain_krom.py`, `osm_layers.py` и планов, которые он читает.

1. Офлайн: `terrain_krom` → `roads_mesh` → `trees_points` → `city_mesh` → `cemetery_points`. Готово — выходы из таблицы шага 2.
   Менялся край Landscape — ещё `horizon_mesh` → (редактор) `horizon_krom`. `furniture_points` рельеф не читает: высоту малым формам даёт трасса `furniture_krom`.
2. Blender: менялась земля под оградами храмов генератора — `python scripts/bl_run.py scripts/blender/pskov_church.py`, потом `heroes_krom`.
3. Редактор: `heights_krom` (ждать `[heights_krom] done` в `Krom.log`) → `landscape_krom` → `blockout_krom` → `walls_krom` → `heroes_krom` → `bridge_krom` → `gabions_krom` → `furniture_krom` → `finpark_krom` → `trees_krom` → `city_krom` → `roads_krom` → `cemetery_krom` → `landmarks_krom`. Готово — `[имя] done` у каждого.
   `blockout_krom`, `walls_krom`, `heroes_krom` нужны, когда земля менялась под стенами или героями.

## Скрипты

### Редактор (ue_run)
| Скрипт | Что делает | Входы → выходы |
|---|---|---|
| `level_krom.py` | уровень `L_Krom`: солнце, небо, облака, дымка, PostProcess, регион загрузки `LoadAll` | пресет `light_krom.DEFAULT` → `/Game/Krom/Maps/L_Krom` |
| `heights_krom.py` | высоты Landscape из heightmap без интерфейса, запись на тиках редактора | `build/terrain/heightmap_L_Krom_rg.png` → Landscape и 64 прокси |
| `horizon_krom.py` | кольцо горизонта: земля и вода за краем Landscape, материал по маске WorldCover | `build/horizon/*` → `/Game/Krom/Environment/Horizon` |
| `materials_krom.py` | материалы зданий по ключам цвета, переназначение слотов мешей Architecture | `refs/textures/textures.json` («buildings») → `/Game/Krom/Materials/Buildings`, `/Game/Krom/Architecture/Textures` |
| `landscape_krom.py` | материал Landscape по двум маскам покрытия, вода на урезе и выше плотины | `refs/dem/*mask*`, `refs/textures`, `build/terrain/water_pools.json`, `build/horizon/horizon.json` → `/Game/Krom/Environment/{Terrain,Water}`, `/Game/Krom/Materials/Terrain` |
| `blockout_krom.py` | blockout из примитивов для зданий без героя и участков стен без меша | `krom_plan` → `/Game/Krom/Blockout` (`M_Blockout`, `MI_BO_*`, `SM_BO_*`) |
| `walls_krom.py` | стены Крома, Довмонтова и Окольного города: меш на участок, земля трассой | `krom_plan`, `okolny_plan`, `wall_mesh` → `/Game/Krom/Architecture/Walls` |
| `heroes_krom.py` | герои из Blender: импорт, материалы по слотам, установка на землю по плану | `build/blender/*.glb`, `krom_plan` → пути `Building.hero` в `/Game/Krom/Architecture` |
| `bridge_krom.py` | мосты через Великую и Пскову: плита, балки, опоры, перила, фонари | OSM (`BRIDGES`) → `/Game/Krom/Environment/Bridges`, `/Game/Krom/Materials/Bridges` |
| `gabions_krom.py` | габионы левого берега Псковы: подпорная стенка у тропы, земля трассой | Landscape, `T_GroundRiprap_D` → `SM_Gabions_Pskova`, `M_KromGabion` |
| `furniture_krom.py` | фонари, скамейки, урны HISM по точкам; модуль: `lights(True)` — вечерний свет | `build/furniture/points.json`, `build/blender/SM_Furn_*.glb` → `/Game/Krom/Environment/Furniture`, `/Game/Krom/Materials/Furniture` |
| `finpark_krom.py` | Финский парк и плотина на Пскове: модели по плану, фонари и скамейки HISM | `finpark_plan`, `build/finpark/*.glb`, `SM_Furn_Bench` → `/Game/Krom/Environment/FinPark` |
| `trees_krom.py` | деревья и кусты HISM по точкам, материалы коры и листвы | `build/trees/points.json`, `build/blender/SM_Tree_*.glb`, `refs/textures/leaves` → `/Game/Krom/Environment/Trees`, `/Game/Krom/Materials/Trees` |
| `city_krom.py` | рядовая застройка мешами клеток: фасады, стёкла, кровли | `build/city/city.json` → `/Game/Krom/Environment/City`, `/Game/Krom/Materials/City` |
| `roads_krom.py` | дороги и дорожки мешами клеток поверх Landscape, разметка материалом | `build/roads/roads.json`, `refs/textures` («roads») → `/Game/Krom/Environment/Roads`, `/Game/Krom/Materials/Roads` |
| `cemetery_krom.py` | Мироносицкое кладбище: надгробия и звенья ограды HISM по точкам | `build/cemetery/points.json`, `build/blender/SM_Cem_*.glb` → `/Game/Krom/Environment/Cemetery` |
| `landmarks_krom.py` | памятные знаки и памятники по плану, высота трассой | `landmarks_plan`, `build/blender/SM_Mark_*.glb` → `/Game/Krom/Environment/Landmarks` |
| `flyover_krom.py` | облёт: камера по опорным точкам `WAYPOINTS`; `storyboard()` — раскадровка | → `/Game/Krom/Cinematics/SEQ_Flyover`, `CAM_Flyover` |
| `cameras_krom.py` | ракурсы-кандидаты `CAM_*` на высоте глаз и их снимки | REFERENCES «Ракурсы-кандидаты» → `CAM_*`, `media/renders/shots/cam_*.png`; сбрасывает очередь `shot_krom` — свои снимки ставить после него |
| `hello_krom.py` | smoke test: куб в начале координат, стрелки на север и восток | → акторы `generated:hello_krom` |
| `palette_krom.py` | модуль: палитра `MPC_KromPalette`, вода `M_KromWater`, импорт текстур, узлы материалов | `krom_plan.COLORS`, `refs/textures/water` → `collection()` обновляет цвета на месте |
| `light_krom.py` | модуль: пресеты времени суток — `apply('day' / 'dawn' / 'sunset')` | акторы `level_krom` → их свойства (сохранить уровень — `save=True`) |
| `shot_krom.py` | модуль: снимок SceneCapture без Lumen для проверки геометрии, асинхронно | `shot(имя)`, `shot_photos()`, ракурсы `VIEWS` → `media/renders/shots/<имя>.png` |
| `view_krom.py` | модуль: снимок вьюпорта с Lumen и облаками, синхронно; `clouds(True)` | `view(имя)` → `media/renders/views/<имя>.png` |
| `budget_krom.py` | модуль: замер GPU и видеопамяти CSV-профайлером — `start()`, потом `report()` | → `Krom/Saved/Profiling/CSV`, медианы кадра |
| `render_krom.py` | модуль: рендер отрезка облёта через MRQ в MP4 — `preview()`, `render()`, `status()` | `SEQ_Flyover` → `media/renders/movies/<name>/<name>.mp4` |

### Офлайн (.venv)
| Скрипт | Что делает | Входы → выходы |
|---|---|---|
| `terrain_krom.py` | рельеф Landscape: FABDEM, берега OSM, местные правила → heightmap и маски покрытия | `refs/dem/fabdem_krom.tif`, `refs/osm`, планы → `refs/dem/heightmap_L_Krom.{png,json}`, `ground_mask{,2}_L_Krom.png`, `build/terrain/*`, превью `media/renders/terrain` |
| `horizon_mesh.py` | кольцо горизонта: сетка FABDEM с кривизной Земли, вода, маска WorldCover | `refs/dem/fabdem_horizon.tif`, `refs/landcover/worldcover_horizon.tif`, heightmap → `build/horizon` |
| `roads_mesh.py` | дороги, тротуары, дорожки, лестницы, «зебры» из OSM: элементы и меши клеток | `refs/osm`, heightmap → `build/roads/roads.json` + превью; `corridors()` — для `terrain_krom` |
| `trees_points.py` | точки деревьев и кустов на Landscape: OSM и WorldCover, с исключениями | `refs/osm`, `refs/dem`, `refs/landcover` → `build/trees/points.json` + превью |
| `city_mesh.py` | рядовая застройка из OSM с фасадным генератором, меши клеток | `refs/osm`, heightmap, `facade_rules` → `build/city/city.json`; `--glb` — клетки ещё и в GLB |
| `cemetery_points.py` | точки надгробий и звеньев ограды Мироносицкого кладбища | `refs/osm`, `build/trees/points.json` → `build/cemetery/points.json` + превью |
| `furniture_points.py` | точки фонарей, скамеек, урн вдоль дорожек: OSM и правила по фото | `refs/osm` → `build/furniture/points.json` + превью |
| `textures_fetch.py` | тайловые текстуры Poly Haven (CC0, 2K) и их средние цвета | сеть → `refs/textures/polyhaven`, `refs/textures/textures.json` |
| `leaf_atlas.py` | процедурный атлас листвы и кора Poly Haven для деревьев | → `refs/textures/leaves/T_LeafAtlas_{D,N}.png`, `refs/textures/trees.json` |
| `water_normals.py` | бесшовная карта нормалей ряби для `M_KromWater` | → `refs/textures/water/T_WaterRipples_N.png`, `water.json` |
| `photo_refs.py` | фото Commons со свободными лицензиями и пары «фото / модель» | `fetch` → `refs/photos/commons` + манифест; `compare` (после `shot_photos()`) → `media/renders/compare` |
| `web_export.py` | лёгкая сцена для веб-просмотрщика three.js, без редактора | `build/*`, `refs/textures`, `web/` → `build/web` (node/npx; `--no-npx` — без сжатия) |

### Планы (чистый Python)
Данные и общие модули без `unreal` и `bpy`; их импортируют скрипты других групп. Запуск `python scripts/<x>.py` — самопроверка или сверка с OSM.

| Скрипт | Что делает | Входы → выходы |
|---|---|---|
| `krom_plan.py` | план Крома и Довмонтова города: башни, участки стен, здания, цвета `COLORS` | REFERENCES → числа всем скриптам |
| `okolny_plan.py` | стена Окольного города по Великой к югу от Ольгинского моста: участки `WallRun` | OSM, REFERENCES → `scene_runs()` для `walls_krom`, `trees_points`, `web_export` |
| `yard_plan.py` | Дом причта, Пороховые погреба, Консистория: габариты, оси, контуры | → `krom_plan.buildings()`, `blender/krom_yard.py` |
| `prikaz_plan.py` | Приказные палаты: габариты, крыльцо, высоты, ось | → `krom_plan.prikaz_palaty()`, `blender/prikaz.py` |
| `pskovgu_plan.py` | главный корпус ПсковГУ и корпус на Поземского, 6 | → `krom_plan.buildings()`, `blender/pskovgu.py` |
| `pozemskogo_plan.py` | герои Запсковья, партия 2: Поземского, 8, 6А, 10, 24 | → `krom_plan.buildings()`, `blender/pozemskogo.py` |
| `zapskovye_plan.py` | первый ряд Запсковья, партия 1: Советская наб., 4, 6, 1/2 и Поземского, 5 | → `krom_plan.buildings()`, `blender/zapskovye.py` |
| `lenina_plan.py` | площадь Ленина: библиотека Василева и «Центр семьи» | → `krom_plan.buildings()`, `blender/lenina.py` |
| `finpark_plan.py` | Финский парк и плотина: что, где и как по высоте ставить | → `finpark_krom`, `blender/finpark.py`; в `.venv` — `build/finpark_refs/plan.png`, `pool_ring.json` |
| `landmarks_plan.py` | памятные знаки: точка, азимут лица, отсчёт высоты | → `landmarks_krom`, `blender/landmarks.py` |
| `facade_rules.py` | стили рядовой застройки: класс здания, окна, цоколь, палитры стен и кровель | → `city_mesh` |
| `osm_layers.py` | слои OSM, классы покрытия земли, ширина и покрытие дорожек, площади | `refs/osm` → `terrain_krom`, `roads_mesh`, `furniture_points` |
| `wall_mesh.py` | геометрия стены участка по высотам земли, без булевых операций | → `walls_krom`, `bridge_krom`, `web_export` |
| `krom_geo.py` | широта/долгота → метры проекта (D-013), разбор выгрузок OSM | `refs/osm` → всем скриптам |

### Blender (bl_run)
Выгрузка — `build/blender/`, превью — `media/renders/blender/`, если в строке не сказано иное. `-- <ключ>` — одна модель (ключи — в докстринге).

| Скрипт | Что делает | Входы → выходы |
|---|---|---|
| `bl_krom.py` | модуль: геометрия в осях здания, выгрузка GLB, превью | → его импортируют все скрипты группы |
| `hello_axes.py` | smoke test конвейера Blender → glTF → UE: метки по осям | → `SM_AxisTest.glb` |
| `cathedral.py` | Троицкий собор | `krom_plan.TRINITY` → `SM_TrinityCathedral.glb` |
| `belfry.py` | колокольня Троицкого собора | `krom_plan.BELFRY` → `SM_TrinityBelfry.glb` |
| `round_tower.py` | круглые башни Крома с тёсовым шатром и сторожевой вышкой | `krom_plan.RoundTowerPlan` → `SM_<Башня>.glb` |
| `facet_tower.py` | гранёные башни: Довмонтова, Власьевская, Рыбницкая | `krom_plan.FacetTowerPlan` → `SM_<Башня>.glb` |
| `paromenye.py` | церковь Успения с Пароменья и её звонница | `krom_plan.PAROMENYE*` → `SM_Paromenye.glb`, `SM_ParomenyeBelfry.glb` |
| `chapels.py` | часовни у Ольгинского моста: Анастасии, Ольгинская | `krom_plan.CHAPELS` → `SM_Chapel_<key>.glb` |
| `pskov_church.py` | генератор «псковского храма»: храмы, звонницы, ограды с воротами | `krom_plan.CHURCHES`, `refs/dem/heightmap_L_Krom.png` → `SM_<key>.glb` |
| `krom_yard.py` | Дом причта, Пороховые погреба, Консистория | `yard_plan` → 3 GLB, превью `build/yard/renders` |
| `prikaz.py` | Приказные палаты | `prikaz_plan` → `SM_PrikazPalaty.glb`, превью `build/prikaz/renders` |
| `pskovgu.py` | корпуса ПсковГУ | `pskovgu_plan` → 2 GLB, превью `build/pskovgu/renders` |
| `pozemskogo.py` | герои Запсковья, партия 2 | `pozemskogo_plan` → 4 GLB, превью `build/pozemskogo/renders` |
| `zapskovye.py` | герои Запсковья, партия 1 | `zapskovye_plan` → 4 GLB, превью `build/zapskovye/renders` |
| `lenina.py` | библиотека Василева и «Центр семьи» на площади Ленина | `lenina_plan` → 2 GLB, превью `build/lenina/renders` |
| `tree.py` | деревья и кусты: ветви трубками, листва карточками по скелетам PVE | скелеты плагина движка PVE, `refs/textures/trees.json` → `SM_Tree_*.glb`, `trees_report.json` |
| `street_furniture.py` | фонари, скамейка, урна | → `SM_Furn_*.glb`, `furniture_report.json` |
| `cemetery.py` | надгробия и звено ограды кладбища | → `SM_Cem_*.glb`, `cemetery_report.json` |
| `landmarks.py` | памятные знаки и памятники по фото | `landmarks_plan` → `SM_Mark_*.glb`, `landmarks_report.json` |
| `finpark.py` | плотина, лестницы, мостики, «корабль», фонарь Финского парка | `finpark_plan` → `build/finpark/SM_FinPark_*.glb`, превью `build/finpark_refs/renders` |

### Утилиты
| Скрипт | Что делает | Входы → выходы |
|---|---|---|
| `ue_run.py` | файл или `-c "код"` — в открытый редактор через Remote Execution | `UE_ROOT` → вывод скрипта, код 0 / 1 / 2 |
| `bl_run.py` | скрипт Blender без окна, `--factory-startup` | `BLENDER` → код 0 / 1 / 2 (2 — Blender не найден) |
| `check_text.py` | управляющие символы и битый UTF-8 в текстовых файлах; хук `pre-commit` | индекс git (`--all` — все файлы) → код 1 и список нарушений |

## Landscape: создание и обновление
Python API UE 5.8 не умеет создавать Landscape, поэтому он создаётся в режиме «Ландшафт» (D-014). Агент делает это сам через `SlateInspectorToolset` (D-015); руками — те же шаги:

1. `.venv\Scripts\python scripts/terrain_krom.py` — heightmap и параметры в `refs/dem/heightmap_L_Krom.json`.
2. Остановить игру (PIE), если запущена: во время игры Landscape не создаётся.
3. Режим «Ландшафт» (Shift+2) → «Проектирование» → «Новый» → **Импорт из файла**.
4. «Файл карты неровностей» — `D:/PskovKrom/refs/dem/heightmap_L_Krom.png` (Enter). Редактор прочтёт 2017 × 2017.
5. «Количество фрагментов на компонент» — **2×2**, «Количество компонентов» — **16 × 16** (итого 256, «Общее разрешение» 2017 × 2017). Кнопку «Подогнать к данным» **не** нажимать — она возвращает 1×1 и 32 × 32.
6. «Расположение» — **0, 0, 0**: это *центр* ландшафта, а не угол. «Масштаб» — 100, 100, 100.
7. «Импорт». Проверка: у актора Landscape Location = (−100800, −100800, 0), 64 LandscapeStreamingProxy; высота у собора — 0 м.
8. `python scripts/ue_run.py scripts/heights_krom.py` — обязательно: кроме высот он снимает у Landscape и 64 прокси флаг `is_spatially_loaded`, иначе в рендере `-game` World Partition стримит их по расстоянию и дальняя земля уходит под воду (D-042, уточнение 2026-09-27). Готово — `[heights_krom] done` в `Krom.log`.
9. Дальше — «Первичная сборка», шаг 4, со строки `horizon_krom`.

Обновить высоты того же размера — раздел «После правки рельефа». Запасной путь руками: режим «Ландшафт» → «Управление» → «Импорт» того же файла.

## Blender → UE: оси и слоты
Импорт `.glb` — `AssetImportTask` (Interchange): StaticMesh с Nanite и MaterialInstance на каждый материал Blender, слоты названы по материалам — по имени слота скрипты UE назначают материалы. Оси: Blender (x, y, z) м → UE (100x, −100y, 100z) см, поэтому точка здания (u, v, z) в Blender — (u, −v, z) (`bl_krom`). Проверено импортом `SM_AxisTest`: bbox (−100, −350, 0)…(550, 100, 500).
