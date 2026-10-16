# EasyVFX — Hiệu ứng đẹp cho Roblox Studio, không cần code

EasyVFX là plugin Roblox Studio giúp người **không biết lập trình** tạo hiệu ứng hình ảnh (VFX) chỉ bằng cách bấm chuột:
chọn vật thể → bấm vào hiệu ứng → đổi màu, kéo thanh trượt → chọn *khi nào* hiệu ứng chạy. Xong.

![Xem trước hình học hiệu ứng](docs/preview-shapes.png)
*Ảnh dựng lại từ dữ liệu của runtime (vòng, lưỡi chém, tia, sét, hố đá) bằng `tools/render_snapshot.py`. Ảnh này là bản xem trước gần đúng, không phải ảnh chụp trong Roblox.*

---

## 1. Cài đặt (1 phút)

**Cách A — thư mục Plugins (khuyên dùng)**
1. Mở Roblox Studio → tab **Plugins** → bấm **Plugins Folder**.
2. Chép file `build/EasyVFX.rbxmx` vào thư mục vừa mở.
3. Khởi động lại Studio. Nút **EasyVFX** sẽ xuất hiện ở tab Plugins.

**Cách B — lưu thành Local Plugin**
1. Kéo file `build/EasyVFX.rbxmx` vào cửa sổ Studio.
2. Chuột phải vào Script `EasyVFX` trong Explorer → **Save as Local Plugin…** rồi xóa bản trong game đi.

Lần đầu mở, plugin sẽ hiện **hướng dẫn 3 bước**. Có thể bỏ qua và xem lại sau trong **Hướng dẫn**.

---

## 2. Dùng thế nào

| Bước | Làm gì |
|---|---|
| 1. Chọn nơi đặt | Click một Part, Model (nhân vật) hoặc Attachment. Không chọn gì thì hiệu ứng đặt **chỗ camera đang nhìn**. Chọn Baseplate (part rất lớn) cũng được tính là "mặt đất". |
| 2. Thêm hiệu ứng | Tab **Thư viện** → tìm theo tên (ví dụ "chém", "sét") hoặc lọc theo nhóm → bấm vào thẻ. Hiệu ứng được thêm ngay, **Ctrl+Z** để hoàn tác. |
| 3. Tùy chỉnh | Tab **Tùy chỉnh** tự mở: đổi **Màu chính / Màu phụ** (bấm ô màu hoặc gõ mã `#FFAA00`), kéo **Kích thước, Số lượng, Tốc độ, Thời gian tồn tại, Độ phát sáng**. |
| 4. Chọn cách kích hoạt | **Luôn bật**, **Lặp lại**, **Khi chạm vào**, **Khi click chuột**, **Khi bấm phím E** (ProximityPrompt), hoặc **Bằng script**. |
| 5. Thử | Nút **Xem thử** phát ngay trong Studio. Bấm **Play (F5)** để chạy thật trong game. |

Mỗi hiệu ứng là **một Part vô hình** tên `VFX_…` — kéo, xoay, nhân bản, xóa như Part bình thường. Chọn lại nó bất cứ lúc nào để chỉnh tiếp.

### 30 hiệu ứng có sẵn

- **Chiến đấu:** Chém lưỡi liềm, Liên hoàn trảm, Va chạm, Đập đất (hố + đá văng), Pháo năng lượng, Vụ nổ, Sét đánh, Sóng xung kích, Vệt vũ khí (Trail).
- **Phép thuật:** Vòng phép, Hồi máu, Lên cấp, Hào quang sức mạnh, Cổng dịch chuyển, Khiên năng lượng, Quả cầu năng lượng, Lấp lánh.
- **Nguyên tố:** Lửa, Khói, Băng giá, Đài phun nước.
- **Môi trường:** Mưa, Tuyết, Đom đóm, Sương mù, Pháo giấy, Bong bóng.
- **Ánh sáng:** Tia laser, Quầng sáng, Viền phát sáng (Highlight).

Hiệu ứng hay dùng có thể bấm **Nâng cao → Lưu vào Yêu thích**, sau đó thêm lại 1 chạm từ đầu tab Thư viện.

---

## 3. Vì sao hiệu ứng trông "sắc nét như làm bằng Blender"?

Texture có sẵn của Roblox khá mờ, nên phần "sắc" của EasyVFX được dựng bằng **hình học**, không dùng ảnh:

| Mảnh | Cách làm | Dùng trong |
|---|---|---|
| **Ring** | 4 Beam cong Bezier (CurveSize = r·4/3·tan(π/8) ≈ 0.5523r), lõi trắng + viền màu, nở ra rồi mờ dần | sóng xung kích, đường hầm vòng, vòng phép |
| **Slash** | Dải Beam cong hình trăng khuyết: nhọn 2 đầu, dày ở đầu lưỡi, đuôi mờ, quét một góc | chém, liên hoàn trảm |
| **Lines** | Kim sáng nhọn 2 đầu bắn ra (hình cầu / vòng / lên trên / phía trước) | va chạm, đập đất, hào quang |
| **Bolt** | Sét zig-zag, đổi hình mỗi ~0.05s, nhấp nháy | sét đánh |
| **Orb** | Part **Neon / ForceField** nở và mờ (quả cầu, cột sáng, lõi tia) | nổ, lên cấp, pháo năng lượng |
| **Crater / Debris** | Đá trồi lên thành vòng rồi lún xuống; đá văng theo quỹ đạo, lấy màu & chất liệu của mặt đất bên dưới | đập đất, vụ nổ |

Thêm vào đó: tia lửa dùng texture vuông kéo dài theo hướng bay (`VelocityParallel` + `Squash`), `LightEmission = 1` để cộng sáng.
**Mẹo:** bấm **Bật Bloom cho Lighting** (trong Nâng cao hoặc Hướng dẫn) để Neon và các vệt sáng rực như anime.

## 3b. Chất lượng HD với Blender (v2)

Bản v1 sắc nét nhưng **thô**. So với ảnh tham khảo (bộ 3 vệt chém vàng/đỏ/tím, pháo năng lượng, đập đất), v1 thua ở 5 điểm:

| Ảnh tham khảo có | v1 (chỉ hình học) | v2 HD (texture Blender) |
|---|---|---|
| Thân vệt chém gồm **nhiều sợi mảnh** sáng tối khác nhau | Dải phẳng một màu | Vân sợi tạo bằng Noise kéo dài trong shader Blender |
| **Đuôi tưa và tan dần**, mép trong lởm chởm | Viền trơn, biến mất đột ngột | Mỗi sợi dài ngắn khác nhau, flipbook 16 khung tan theo noise |
| **Mép ngoài sáng gắt + quầng glow** ôm sát | Không có glow, lõi đều | Viền sáng gắt + glow mềm trong texture, LightEmission cộng sáng |
| **Lóe trắng → màu → tắt** rất nhanh | Màu cố định, giữ lâu | Màu theo thời gian: trắng → màu chính → màu phụ trong 0.35 giây |
| **Sao lấp lánh rải dọc vệt** | Tia lửa bắn từ tâm | Sao 4 cánh sắc rải dọc cung + tia lửa |

![So sánh theo thời gian](docs/compare-slash-timeline.png)
![So sánh 9 hiệu ứng](docs/compare-grid.png)
![Liên hoàn trảm HD](docs/hd-flurry.png)

*Các ảnh trên được dựng bằng Blender Cycles từ **dữ liệu thật mà runtime EasyVFX sinh ra** (`tests/snapshot.luau` → `tools/blender_preview.py`). Script mô phỏng lại hạt theo thuộc tính Roblox (tốc độ, drag, size/transparency theo thời gian, flipbook, hướng quad). Đây là ảnh gần đúng, **không phải ảnh chụp trong Roblox**.*

### Bật HD (một lần, dùng được cho mọi place)

1. Studio → **File → Import 3D** → chọn `pack/EasyVFX_Pack.fbx` → **Import**. Studio sẽ upload các texture nhúng trong file.
2. Plugin → tab **Thư viện** → thẻ **Chất lượng HD** → bấm **Quét gói**. Plugin tìm các part `EVFX_Tex_*` và đọc ID ảnh, rồi tự cập nhật mọi hiệu ứng.
3. Có thể xóa model vừa import. ID ảnh được lưu trong cài đặt plugin nên place khác dùng lại được ngay.

Nếu Quét gói không tìm thấy ID (Import 3D đôi khi không gán texture), hãy dùng **Asset Manager → Bulk Import** cho thư mục `pack/textures/`. Sau đó bấm **Dán ID** và nhập mỗi dòng một cặp, ví dụ `slash_arc = 1234567890` (tên = tên file không có `.png`). Bắt buộc có `slash_arc` thì HD mới bật.

Khi HD bật:
- 8 preset có lớp HD riêng: Chém lưỡi liềm, Liên hoàn trảm, Va chạm, Đập đất, Vụ nổ, Sét đánh, Pháo năng lượng, Sóng xung kích.
- Mọi preset khác tự đổi texture mờ mặc định của Roblox (sao, quầng sáng, tia vuông) sang bản sắc nét.
- Tắt HD thì hiệu ứng trở về bản cơ bản, không mất gì.

Lưỡi chém HD là hạt phẳng (`VelocityPerpendicular`). Nếu trong Studio cung bị lệch hướng so với ý bạn, dùng thanh trượt **Góc xoay** trong tab Tùy chỉnh.

### Gói HD gồm gì

![Gói texture HD](docs/hd-pack.png)

| Texture | Dùng cho |
|---|---|
| `slash_arc` (1024², vân sợi uốn cung) | Thân lưỡi chém HD |
| `flip_slash` (flipbook 4×4) | Lưỡi chém hiện ra rồi tan dần |
| `flip_impact`, `flip_smoke`, `flip_electric` (4×4) | Va chạm nổ tia, bụi khói, tia điện |
| `ring_wave` | Vòng sóng có noise trên mặt đất |
| `spark_star`, `spark_streak`, `glow_soft` | Sao lấp lánh, tia lửa, quầng sáng |
| `slash_fiber`, `slash_clean`, `slash_glow`, `slash_core` | Texture dải thẳng cho Beam/Trail/mesh |
| Mesh `EVFX_Mesh_SlashWide`, `SlashThin`, `SpinRing` | Lưỡi chém 3D có UV, dùng với tính năng mesh bên dưới |

![Ảnh dựng Blender của các lớp lưỡi chém](docs/hd-slash-colors.png)
*Ảnh dựng thử trong Blender: lớp glow, vân sợi, lõi và sao, với 3 màu giống ảnh tham khảo.*

### Tự tạo lại / chỉnh gói bằng Blender của bạn

Script là Python thuần cho Blender (4.2+ hoặc 5.x), không cần addon:

```bash
blender -b -P blender/make_vfx_pack.py -- --out ./pack            # render toàn bộ gói + FBX
blender -b -P blender/make_vfx_pack.py -- --out ./pack --only slash_arc,flip_slash --samples 64
```

Hoặc mở Blender → tab **Scripting** → mở file → **Run Script**. Hình dạng nằm trong hàm `slash_shape()`: độ dày, độ dài sợi (`fib_n`), độ tưa đuôi (`tail`), và mép trong (`reach`). Đổi các số ở đó rồi chạy lại để có phong cách riêng.

### Dùng mesh làm trong Blender

Đặt một **MeshPart** (vd. lưỡi chém xuất từ Blender) bên trong Part `VFX_…`, thêm thuộc tính (Attributes) `VFX_Mesh = true`. Khi hiệu ứng chạy, runtime sẽ sao chép mesh rồi phóng to, xoay và làm mờ nó. Các thuộc tính tùy chọn: `Scale0` (mặc định 0.6), `Scale1` (1.4), `SpinDeg` (Vector3, mặc định 0,90,0), `AnimDuration` (0.5s), `EmitDelay`, `BaseTransparency`. Nên đặt `Transparency = 1` cho mesh gốc để nó không hiện khi chưa chạy.

---

## 4. Tối ưu hiệu năng (theo khuyến nghị của Roblox DevForum)

- **Hiệu ứng chạy trên máy người chơi (client).** Khi bị kích hoạt từ server (chạm, click, phím E), server chỉ gửi **một RemoteEvent nhỏ**. Mỗi client tự tạo và tự hoạt hình hiệu ứng, nên server không phải tạo instance và mạng không phải gửi part chuyển động.
- **Hiệu ứng "Lặp lại" chạy hẳn trên client**, nên không tốn băng thông mạng.
- **Tự giảm chất lượng** khi người chơi chọn Graphics thấp: số hạt, kim sáng và đá giảm theo (`EasyVFX.Quality`).
- **Mảnh tạm** nằm trong Camera, có `Archivable = false`, `CanCollide/CanTouch/CanQuery = false` và không đổ bóng. Chúng không được lưu vào place và không cản raycast của gameplay.
- **Một vòng lặp hoạt hình duy nhất** cho tất cả hiệu ứng. Không tạo tween hay luồng (thread) riêng cho từng mảnh. Đá văng dùng quỹ đạo tính tay, không dùng physics.
- Rate của emitter bị giới hạn ở 400. Đá/tia mỗi lớp tối đa 64.
- Dùng **quy ước thuộc tính của cộng đồng**: `EmitCount`, `EmitDelay`, `EmitDuration`. Vì vậy hiệu ứng EasyVFX tương thích với các plugin Emit khác và ngược lại.

---

## 5. Cho người biết code (không bắt buộc)

Plugin tự cài 3 thứ vào game **một lần duy nhất**, khi bạn thêm hiệu ứng đầu tiên:

| Đối tượng | Vị trí | Vai trò |
|---|---|---|
| `EasyVFX` (ModuleScript) | ReplicatedStorage | Runtime phát hiệu ứng + API |
| `EasyVFXServer` (Script) | ServerScriptService | Gắn các kích hoạt chạm / click / phím E |
| `EasyVFXClient` (LocalScript) | StarterPlayerScripts | Phát hiệu ứng trên máy người chơi, chạy vòng lặp |

```lua
local EasyVFX = require(game.ReplicatedStorage.EasyVFX)

EasyVFX.Play(workspace.Sword.VFX_CrescentSlash)              -- phát tại chỗ (server: phát cho mọi người)
EasyVFX.Play("VFX_Explosion", CFrame.new(0, 5, 0))           -- phát một bản sao ở vị trí khác
EasyVFX.SetEnabled(workspace.Torch.VFX_Fire, false)          -- tắt các lớp luôn bật
```

Chọn kích hoạt **Bằng script** thì plugin sẽ hiện sẵn dòng code đúng đường dẫn để bạn dán vào. Mọi thông số của hiệu ứng đều lưu trong Attributes `VFX_*` của Part, có thể sửa trong cửa sổ Properties.

---

## 6. Giao diện

Thiết kế theo skill **UI UX Pro Max** (design system *Minimalism & Swiss Style*, bảng màu *Developer Tool / IDE*: nền slate, nút hành động xanh lá, mật độ dày kiểu dashboard):
- Song ngữ **Tiếng Việt / English** (nút VI/EN), tự theo theme Sáng/Tối của Studio.
- Mọi ô nhập đều có nhãn hiển thị và dòng gợi ý. Có thể gõ số chính xác bên cạnh thanh trượt.
- Phần **Nâng cao** được thu gọn để người mới không bị ngợp. Hướng dẫn 3 bước có thể bỏ qua.
- Có thông báo sau mỗi thao tác, xác nhận 2 lần trước khi xóa, và Ctrl+Z dùng được cho mọi thao tác.
- Không dùng emoji làm icon. Nút hover có chuyển động 120–180 ms.

---

## 7. Cấu trúc mã & kiểm thử (cho người phát triển)

```
src/Plugin/
  init.server.luau        plugin: toolbar, dock panel, chèn hiệu ứng, undo, cài runtime
  Shared/Presets.luau     30 preset (dữ liệu thuần)
  Shared/Builder.luau     preset + thông số -> instance (cập nhật tại chỗ, không giật)
  Shared/Strings.luau     chữ tiếng Việt / tiếng Anh
  Runtime/EasyVFX.luau    runtime: emit, Ring/Slash/Lines/Bolt/Orb/Debris/Crater, kích hoạt
  Runtime/EasyVFXServer.server.luau, EasyVFXClient.client.luau   (tắt trong plugin, bật khi cài vào game)
  UI/Theme.luau, Components.luau, App.luau
blender/    make_vfx_pack.py (tạo gói HD: texture, flipbook, mesh, FBX)
pack/       gói HD đã render sẵn: EasyVFX_Pack.fbx + textures/*.png
tests/      run.luau (builder+runtime), ui.luau (bấm thử toàn bộ GUI), snapshot.luau (xuất dữ liệu runtime)
tools/      blender_preview.py, render_snapshot.py, view_textures.py, check.sh
```

Công cụ cần có: [Rojo](https://github.com/rojo-rbx/rojo) 7.4, [Lune](https://github.com/lune-org/lune) 0.8, [luau-lsp](https://github.com/JohnnyMorganz/luau-lsp) (kèm `globalTypes.d.luau`).

```bash
rojo build default.project.json -o build/EasyVFX.rbxmx   # build plugin
lune run tests/run.luau        # 1229 kiểm tra: tạo/cập nhật/phát/dọn dẹp mọi preset, cả Basic lẫn HD
lune run tests/ui.luau         # 856 kiểm tra: bấm thử mọi nút, tab, thanh trượt, kích hoạt, thẻ HD
tools/check.sh                 # chạy tất cả + type-check

# Dựng ảnh preview bằng Blender từ dữ liệu runtime (pip install bpy, hoặc chạy bằng blender -b -P)
lune run tests/snapshot.luau snap.json hd                       # hoặc: basic / thêm "slash 2,4,6" để chụp theo thời gian
python tools/blender_preview.py snap.json out/ pack/textures <thư mục texture có sẵn của Roblox đã đổi sang png>
```

Các test chạy bằng Lune, với Instance Roblox thật từ reflection database (sai tên hoặc sai kiểu thuộc tính sẽ báo lỗi). Các hàm của engine (`Emit`, `Raycast`, sự kiện GUI) được giả lập. Ánh sáng và render thật vẫn cần thử trong Studio.

---

## Nguồn tham khảo

- Roblox Creator Docs: [Particle emitters](https://github.com/Roblox/creator-docs/blob/main/content/en-us/effects/particle-emitters.md), [Beams (Bezier curve)](https://github.com/Roblox/creator-docs/blob/main/content/en-us/effects/beams.md), [Trails](https://github.com/Roblox/creator-docs/blob/main/content/en-us/effects/trails.md), [Explosion VFX tutorial](https://create.roblox.com/docs/tutorials/use-case-tutorials/vfx/use-particles-for-explosions)
- DevForum, chạy VFX trên client: [Client-Sided VFX](https://devforum.roblox.com/t/client-sided-vfx/2792835), [VFX fire from client recommended?](https://devforum.roblox.com/t/vfx-fire-from-client-recommended-why-or-server-ok/3660009), [Remote events for effects](https://devforum.roblox.com/t/is-using-remote-events-to-play-effects-on-the-client-resource-efficient/3754781), [Optimize VFX at low graphics](https://devforum.roblox.com/t/how-to-optimize-vfx-and-retain-quality-at-low-graphics/2804870)
- DevForum, vòng tròn bằng Beam: [Creating a circular beam](https://devforum.roblox.com/t/creating-a-circular-beam/2436266), [Circle shape with Beam](https://devforum.roblox.com/t/circle-shape-with-beam/228156), [Beam ring tween](https://devforum.roblox.com/t/beam-ring-improvement/3980748)
- DevForum, quy ước EmitCount/EmitDelay: [Jad's Emit Plugin](https://devforum.roblox.com/t/dear-vfx-makers-i-present-to-you-jads-emit-plugin/1986838), [VFX Editor](https://devforum.roblox.com/t/vfx-editor-all-your-vfx-needs-in-one/3103467), [How can I emit particles properly](https://devforum.roblox.com/t/how-can-i-emit-particles-properly/3548786)
- DevForum, đá / hố kiểu anime: [Rock Module](https://devforum.roblox.com/t/rock-module-v10-craters-explosions-and-more-effects/3041562), [Crater system](https://devforum.roblox.com/t/crater-system-by-frodev/2628508), [Anime VFX beginner guide](https://devforum.roblox.com/t/full-beginners-guide-on-scripting-animefighting-vfxvisual-effects-part-1/1610853)
- DevForum, chém bằng mesh/Blender: [Animated slash effects with Blender](https://devforum.roblox.com/t/how-to-make-animated-slash-effects-with-only-blender/1794034), [Animated Slashes 2.0](https://devforum.roblox.com/t/how-to-make-animated-slashes-20/1880010)
- Kỹ thuật slash gradient + noise + dissolve: [Godot Slash Shader](https://godotshaders.com/shader/slash-shader/), [Unity VFX Stylized Ground Slash (Udemy)](https://www.udemy.com/course/unity-vfx-stylized-ground-slash/), [Realtime VFX – Sword Slash help](https://realtimevfx.com/t/sword-slash-help/9407)
- Flipbook / texture trong Roblox: [Create basic visual effects](https://create.roblox.com/docs/tutorials/curriculums/core/building/create-basic-visual-effects), [How to create VFX? (DevForum)](https://devforum.roblox.com/t/how-to-create-vfx/4029502), [LightEmission với màu đen](https://devforum.roblox.com/t/when-coloring-particles-with-lightemission-1-to-black-they-become-transparent/2614320)
- Blender: [bpy trên PyPI](https://pypi.org/project/bpy/)
- Design system: [UI UX Pro Max skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill)
