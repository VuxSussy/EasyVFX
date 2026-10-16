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

### Muốn đẹp hơn nữa: bộ texture sắc nét (tùy chọn)

![Bộ texture](docs/texture-pack.png)

Thư mục `textures/` có 6 ảnh trắng nền trong (flare, impact_burst, ring, slash, star4, streak). Ảnh trắng sẽ nhận màu của hiệu ứng.
1. Studio → **Asset Manager** → **Bulk Import** → chọn các file trong `textures/`.
2. Chuột phải ảnh → **Copy ID**.
3. Trong plugin: **Tùy chỉnh → Nâng cao → Texture riêng** → dán ID.

Ảnh bạn tự vẽ (Blender, Photoshop, Krita…) cũng dùng được y hệt. Có thể tạo lại bộ ảnh bằng `python3 tools/make_textures.py textures`.

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
tests/      run.luau (builder+runtime), ui.luau (bấm thử toàn bộ GUI), snapshot.luau (xuất hình học)
tools/      render_snapshot.py, make_textures.py, check.sh
```

Công cụ cần có: [Rojo](https://github.com/rojo-rbx/rojo) 7.4, [Lune](https://github.com/lune-org/lune) 0.8, [luau-lsp](https://github.com/JohnnyMorganz/luau-lsp) (kèm `globalTypes.d.luau`).

```bash
rojo build default.project.json -o build/EasyVFX.rbxmx   # build plugin
lune run tests/run.luau        # 987 kiểm tra: tạo/cập nhật/phát/dọn dẹp mọi preset
lune run tests/ui.luau         # 847 kiểm tra: bấm thử mọi nút, tab, thanh trượt, kích hoạt
tools/check.sh                 # chạy tất cả + type-check
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
- Design system: [UI UX Pro Max skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill)
