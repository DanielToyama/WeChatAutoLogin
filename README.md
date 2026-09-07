# WeChatAutoLogin — 微信自动登录辅助

开机后微信自动启动却停在登录页、要手动点绿色「登录」按钮？这个程序帮你自动点掉它：
检测到微信登录窗口 → 模板匹配找到绿色按钮 → **通过窗口消息点击（全程不移动你的鼠标）**
→ 检测窗口变大确认登录成功。

## 解决的问题

1. **手动点按钮**：登录页出现后自动点击绿色「登录」按钮，无需人工介入。
2. **鼠标晃动丢点击**：默认 `message` 模式把点击消息直接投递给微信窗口，光标完全不动，
   鼠标怎么晃都不影响。
3. **被遮挡/不在最前方**：先检测并置顶微信窗口；消息点击本身不依赖前台，窗口被盖住也能点。

## 特性

- 等待微信进程与登录窗口出现（超时时间可调；`--watch` 失败自动重试）
- 多尺度模板匹配定位绿色按钮（`greenButton.jpg`，适应不同显示缩放）
- 微信不在最前方时：`message` 模式**无需置顶**（点击消息直接投递给窗口句柄，
  与前台/z 序/遮挡无关，不抢焦点）；其它模式自动置顶
- 不抢鼠标：默认窗口消息点击（另有触屏注入（未测试通过，可能不可用） / SendInput 原子点击（标准鼠标点击）可选）
- 点击后验证登录：窗口变大（或登录窗口关闭且进程存活）
- 已登录时数秒内直接退出，绝不误点

## 环境要求

- Windows 10 / 11
- Python 3.10+
- 安装依赖：`pip install -r requirements.txt`

## 快速开始

**源码版（需要 Python）**

```bat
python wechat_autologin.py --dry-run     :: 只检测不点击（安全）
python wechat_autologin.py               :: 运行一次
python wechat_autologin.py --watch       :: 失败后循环重试，直到登录成功
```

**单文件 exe 版（开箱即用，不需要 Python）**——见下一节。

## 单文件 exe（开箱即用）

`dist\WeChatAutoLogin.exe` 是打包后的单文件程序，**目标机器无需安装 Python**，复制 exe 即可运行。

**直接双击 exe（不带参数）→ 交互菜单**，按数字键直接跳转：

```
  1. 测试微信点击（只检测，不实际点击）
  2. 实操：微信点击登录
  3. 开机自启动设置（自动检测；可安装/取消，自动弹 UAC 提权）
  4. 退出
  5. 打开 GitHub 页面
```

命令行参数与源码版一致（开机自启/静默场景用）：

```bat
WeChatAutoLogin.exe --dry-run     :: 只检测不点击（安全）
WeChatAutoLogin.exe --watch       :: 静默自动登录，失败循环重试（开机自启用这个）
```

**菜单实际显示示意**（双击 exe 后）：

    ==================================================
      WeChatAutoLogin — 微信自动登录辅助
      作者: Daniel_兔兔
      项目: https://github.com/danieltoyama/WeChatAutoLogin
    --------------------------------------------------
      功能: 等待微信登录窗口 -> 模板匹配绿色按钮
            -> 窗口消息点击(不抢鼠标) -> 验证登录成功
    --------------------------------------------------
      1. 测试微信点击（只检测，不实际点击）
      2. 实操：微信点击登录
      3. 开机自启动设置（检测/安装/取消）
      4. 退出
      5. 打开 GitHub 页面
    --------------------------------------------------

按数字键直接执行（无需回车）；操作 3 会先检测自启动现状，安装/取消时自动弹
UAC 提权，并在当前窗口核对显示最终结果。

- 绿色按钮模板 **greenButton.jpg 已内嵌在 exe 里**；微信更新后想换模板，
  把新裁剪的 `greenButton.jpg` 放到 exe 旁边即可覆盖内嵌版。
- 想调整参数（超时、点击方式等），在 exe 旁边放一个 `config.json` 即可覆盖默认值。
- 日志写在 exe 同目录的 `wechat_autologin.log`。

**自己重新打包**（可选）：

```bat
pip install pyinstaller
:: 可选：下载 upx（https://github.com/upx/upx/releases 的 win64.zip）并解压，然后：
python -m PyInstaller --onefile --name WeChatAutoLogin --add-data "greenButton.jpg;." ^
  --upx-dir "upx的解压目录\upx-x.x.x-win64" --clean --noconfirm wechat_autologin.py
```

产物在 `dist\WeChatAutoLogin.exe`：**加 UPX 约 50 MB，不加约 67 MB**（UPX 在构建期
压缩 exe 内部的 DLL，实测省约 17 MB）。
> **UPX 正确用法**：把它作为 `--upx-dir` 交给 PyInstaller 在构建期使用；**不要**再对
> 最终 exe 手动跑 upx——PyInstaller 6 的 exe 启用了 Control Flow Guard，外层 PE 压缩
> 会报 `GUARD_CF not supported`。**注意**：单文件 exe 偶有杀软误报（UPX 压缩略增概率），
> 发布给他人前建议先用 VirusTotal 确认，或加白名单。

## 开机自启（两种方式）

**方式 A：启动文件夹（简单，够用）**

1. 让 `start.bat` 和 `wechat_autologin.py` 保持在同一目录
   （exe 版直接把 `WeChatAutoLogin.exe` 的快捷方式放进启动文件夹即可）。
2. `Win+R` → 输入 `shell:startup` → 回车，打开启动文件夹。
3. 把 **`start.bat` 的快捷方式**放进去。（按住 alt 拖动生成快捷方式）
   程序会通过 `pythonw` 静默运行（`--watch` 模式），直到点绿按钮完成登录。
   如果文件放在别处，修改 `start.bat` 里的 `SCRIPT` 路径。

**方式 B：任务计划程序（启动更早、更可靠，推荐）**

启动文件夹里的程序要等 Explorer 和整套登录流程跑完才被拉起；任务计划程序的
「登录时」触发器由计划任务服务**更早、更稳定**地启动，优先度更高。脚本自身
带等待与 `--watch` 重试，不会和微信抢启动时间。

- 双击 **`install_task.bat`** 注册任务 `WeChatAutoLogin`（自动计算脚本绝对路径）。
  部分系统限制标准用户创建计划任务（组策略/加固），安装器会自动请求管理员权限
  （弹一次 UAC），授权后即注册成功；**任务本身仍在你账号登录时运行，无需常驻管理员**。
- 任务行为：登录后**延迟 5 秒**启动（改 `install_task.ps1` 顶部的 `$delaySec`
  可调；0 = 登录立即启动），以 `pythonw --watch` 静默运行，直到登录成功。
- 卸载：双击 **`uninstall_task.bat`**（同样会自动请求管理员权限）。
- 查看任务详情：`schtasks /Query /TN WeChatAutoLogin /V /FO LIST`

## 典型运行流程（实测记录）

以本机实测为例（微信 4.x，登录页 296×388，message 模式）：

1. 开机后自动运行（`--watch` 或任务计划程序）。
2. 检测到登录窗口，`PrintWindow` 抓图，模板匹配得分 **1.000**。
3. 记录窗口位置 rect；微信不在最前方时 message 模式**无需置顶**，直接向窗口
   投递点击消息（如 `(2879, 622)`），**鼠标光标全程未移动**。
4. 点击后约 3~5 秒：登录窗口关闭、主窗口出现，尺寸 296×388 → **512×894**，
   程序输出「登录成功」并退出（退出码 0）。
5. 已登录状态下再运行：数秒内直接退出，绝不误点。

## 项目文件清单

| 文件 | 说明 |
|---|---|
| `wechat_autologin.py` | 主程序（检测 / 匹配 / 点击 / 验证 / 交互菜单） |
| `config.json` | 可调参数（缺失时使用内置默认值） |
| `greenButton.jpg` | 绿色按钮模板（微信 4.x；改版后自行重新裁剪） |
| `start.bat` | 便捷启动器（pythonw 静默 `--watch`） |
| `install_task.bat` / `install_task.ps1` | 任务计划程序自启动安装（自动提权） |
| `uninstall_task.bat` / `uninstall_task.ps1` | 任务计划程序自启动卸载 |
| `run_test.bat` | 前台测试运行 |
| `requirements.txt` | Python 依赖 |
| `WeChatAutoLogin.exe` | 打包产物（约 50 MB，见上文构建方法；不随源码提交） |

## 工作原理

1. 等待微信进程（`Weixin.exe` / `WeChat.exe`）。
2. 用 `PrintWindow` 抓取窗口画面，和 `greenButton.jpg` 做多尺度模板匹配
   （TM_CCOEFF_NORMED）。
3. 记录窗口位置 rect；微信不在最前方时：`message` 模式直接投递点击消息，
   无需置顶、不抢焦点；其它模式先置顶再点。
4. 按 `click_method` 配置点击按钮中心：
   - `message`（**默认**）— 投递 `WM_MOUSEMOVE / WM_LBUTTONDOWN / WM_LBUTTONUP`
     给微信窗口。**光标零移动**，不怕遮挡。
   - `touch` — Windows 触屏注入（同样不碰鼠标；部分系统/会话不支持，会自动回退）。
   - `mouse` — SendInput 原子点击（MOVE+按下+抬起一次调用完成，光标会瞬移一下，
     但鼠标再晃也不会丢点击）。
5. 验证：`post_click_timeout` 秒内出现面积 ≥ `growth_ratio` 倍的微信窗口，
   或登录窗口关闭且进程仍在，即判定登录成功。

## 配置（config.json）

| 参数 | 默认 | 说明 |
|---|---|---|
| `process_names` | Weixin.exe, WeChat.exe | 等待的微信进程名 |
| `template_file` | greenButton.jpg | 绿色按钮模板图片 |
| `match_threshold` | 0.85 | 模板匹配得分阈值 |
| `match_scales` | 0.75…1.5 | 搜索的缩放档位（应对 DPI 缩放） |
| `click_method` | message | `message`（不碰鼠标、不置顶）/ `touch`（触屏注入）/ `mouse`（原子鼠标） |
| `process_wait_timeout` | 300 | 等待微信启动的秒数 |
| `window_wait_timeout` | 120 | 等待登录页出现的秒数 |
| `max_click_attempts` | 4 | 点击最大尝试次数 |
| `post_click_timeout` | 15 | 点击后观察登录成功的秒数 |
| `growth_ratio` | 1.2 | 窗口面积增长多少倍视为登录成功 |
| `login_max_area` | 350000 | 发现远大于登录页的窗口即认为已登录，立即退出 |
| `min_window_area` | 20000 | 忽略面积过小的窗口（像素²） |
| `pre_click_delay` | 0.6 | 置顶后等待窗口重绘的秒数 |
| `verify_poll_interval` | 0.5 | 登录结果轮询间隔（秒） |
| `no_window_grace` | 8 | 连续无微信窗口多少秒视为已登录，提前退出 |
| `watch` / `watch_interval` | false / 30 | 失败重试循环（`--watch` 用） |

## 已知限制

- **模板依赖版本**：`greenButton.jpg` 对应微信 4.x 登录页；微信改版后匹配得分会
  低于阈值，重新裁剪图片即可（见常见问题）。
- **触屏注入（touch）依赖环境**：部分系统/会话不支持 `InjectTouchInput`（实测本机
  返回 `ERROR_INVALID_PARAMETER`），会自动回退为鼠标模式。
- **单文件 exe 首次启动稍慢**：PyInstaller 需先解包到临时目录（一般 1~2 秒）。
- **计划任务需管理员**：部分系统限制标准用户创建计划任务（组策略/加固），安装时
  自动弹 UAC 提权一次；任务本身在你账号登录时运行，无需常驻管理员。
- **杀软误报**：PyInstaller 单文件 exe 偶被误报（UPX 压缩会略增概率），建议加
  白名单或用 VirusTotal 确认。

## 常见问题

- **匹配得分低 / 找不到按钮**：微信更新会改 UI。登录页出现时重新裁剪绿色按钮，
  保存为 `greenButton.jpg`（与脚本同目录），再跑 `python wechat_autologin.py --dry-run`，
  在 `wechat_autologin.log` 里看得分（≥ 0.85 即可靠）。
- **需要手机确认**：部分账号点击后要手机确认，窗口不会马上变大；`--watch` 会持续重试，
  手机确认后即完成登录。
- **已经登录**：程序数秒内直接退出，什么都不做。
- **杀软误报怎么办**：把 exe 加入白名单，或改用源码版（`python wechat_autologin.py`）。
- **为什么计划任务要管理员**：部分系统（组策略/加固）限制标准用户创建计划任务；
  安装器自动 UAC 提权一次，之后运行不需要管理员。
- **不小心开了两个程序**：内置单实例锁，重复启动会直接退出，不会重复点击。

## 免责声明

本工具用于在你自己电脑上自动化点击微信登录按钮。请合理使用，风险自负。
内置的 `greenButton.jpg` 对应微信 4.x，版本不同可自行重新裁剪。

## 许可与作者

- 作者：**Daniel_兔兔**（GitHub: [danieltoyama](https://github.com/danieltoyama)）
- 许可证：**MIT**（见 `LICENSE`）

有任何问题或建议，欢迎到 [Issues](https://github.com/danieltoyama/WeChatAutoLogin/issues) 反馈。