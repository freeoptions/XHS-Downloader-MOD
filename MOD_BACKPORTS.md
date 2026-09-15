# XHS-Downloader-MOD 上游回补清单

本文档记录本项目相对官方 XHS-Downloader 的固定改动。以后官方发布新版本时，先以官方新版本为基础，再按本文档回补，避免在旧版本上持续堆叠补丁。

## 当前基线

- 上游来源：`JoeanAmier/XHS-Downloader`
- 当前采用版本：官方 2.8
- 当前上游提交：`47840a1`（`upstream/master` / `upstream/develop`）
- 本次工作分支：`codex/upstream-2.8-backport`
- 本地回补提交来源：
  - `df06e36`：2026-08-02 本地功能修改
  - `1d9f7a3`：项目规则补充
  - `da4afd1`：失败作品重试队列补充

官方 2.8 已经包含新的 GUI 页面。本项目直接采用其 `source/GUI`、`static/GUI` 和 GUI 启动入口，附件截图只作为视觉参考，不作为代码指令或配置来源。

## 必须保留的 MOD 功能

### 1. 构建和部署约束

- 使用作者官方 cx_Freeze 完整目录构建方式，不改成 onefile。
- 构建目录为 `dist/XHS-Downloader`，主程序名为 `XHS-Downloader-MOD.exe`。
- 发布或部署时保留完整运行目录和 `Volume` 数据，不只复制 EXE。
- 正式安装目录为 `D:\@Software\XHS-Downloader-MOD`。
- `Volume` 中的配置、下载记录、映射数据和日志必须保留。
- 未明确收到“11”“构建”或“打包”前，不构建最终产物、不启动 EXE。

涉及文件：`setup.py`、`.github/workflows/`、`build_exe.ps1`、`AGENTS.md`。

### 2. 下载默认值和格式策略

- 默认图片格式为 `PNG`。
- 正常下载不使用全局 `AUTO`。
- 只有 `ci.xiaohongshu.com` 的 PNG 转换地址在重试后明确失败时，当前这一张图片才允许改用 `sns-img-bd.xhscdn.com` 的 AUTO 地址重试。
- 回退不得修改全局配置，也不得影响同一作品的其他图片。
- 保留本项目的工作目录、作者归档、文件夹模式、记录作品数据和写入修改时间等默认值。

涉及文件：`source/module/settings.py`、`source/module/manager.py`、`source/application/download.py`。

### 3. 请求失败诊断

- 记录 HTTP 状态、最终页面路径、跳转次数、响应大小、页面标题、错误码和作品字段标记。
- URL 查询参数不写入诊断文本，避免泄露 `xsec_token` 等临时凭据。
- 解析失败时将诊断写入 `Volume/Logs/request_failures.log`，并在日志中提示位置。

涉及文件：`source/application/request.py`、`source/application/app.py`。

### 4. 作品读取失败重试队列

- 首轮处理结束后，只把“读取失败”加入重试队列；下载失败不重复触发作品读取。
- 重试前使用较长随机等待，作品之间继续间隔等待。
- 404 或明确跳转到不可访问页的作品保留为最终失败，不进入等待队列。
- 最终失败链接保存到 `XHS.last_failed_urls`，TUI 可复制失败链接。
- 重试使用独立的较短请求超时，避免单个失效链接长期阻塞。

涉及文件：`source/application/app.py`、`source/TUI/index.py`、`tests/test_retry_queue.py`。

### 5. TUI 和记录维护

- TUI 保留失败链接复制入口。
- 下载记录页面保留“清空全部下载记录”，并区分“记录已清空”和“硬盘同名文件仍存在”。
- 配置输入继续兼容旧配置，并将非法值回退到安全默认值。

涉及文件：`source/TUI/index.py`、`source/TUI/record.py`、`source/TUI/setting.py`、`tests/test_recorder.py`。

## 已从官方 2.8 直接采用的功能

以下功能不再重复实现本地版本，后续优先跟随上游：

- 新版 GUI 页面和任务队列界面；
- 视频封面下载选项；
- `curl_cffi` 请求和浏览器模拟 `impersonate`；
- 请求代理与文件下载代理分离；
- 下载缓冲、断点 Range 和进度回调；
- 脚本服务端队列、来源校验和任务回调；
- 动图、视频直链、RedNote、指定图片序号等 2.8 处理逻辑；
- 文件命名字段拖拽排序、设置页面和 GUI 日志/历史页面。

这些功能的主要来源文件包括 `source/GUI/`、`static/GUI/`、`source/module/manager.py`、`source/application/download.py`、`source/application/image.py`、`source/module/script.py`。

## 冲突处理原则

| 冲突位置 | 处理原则 |
| --- | --- |
| 资源路径 | `ROOT` 指程序/资源根目录，`VOLUME` 指数据目录；源码、cx_Freeze 和冻结运行都要成立 |
| 请求层 | 保留上游 `curl_cffi`、`impersonate`、站点 Referer 和代理行为，再叠加本地诊断 |
| 下载层 | 保留上游缓冲、Range、封面和进度回调，再叠加“单张 PNG 失败才 AUTO” |
| 批量提取 | 保留上游回调和 GUI 任务状态，再叠加本地失败队列；不得使用可变统计默认参数 |
| 配置默认值 | 以本项目的 PNG、Volume 和部署约束为准；上游新增配置字段要补入读取、保存和 GUI |
| 前端页面 | 2.8 GUI 直接跟随上游；本地 TUI 只保留项目已有的诊断和记录维护功能 |
| 数据安全 | 不把 Cookie、Token、完整带参数 URL 或运行日志写入源码、文档或提交 |

## 后续升级流程

1. 读取新版本发布说明，确认新版本提交和新增配置字段。
2. 更新上游引用：

   ```text
   git fetch upstream master --tags
   git show upstream/master
   ```

3. 从上游新提交创建新分支，不直接覆盖当前分支。
4. 按本项目的本地提交顺序回补：构建/配置与可靠性功能，再回补测试和项目规则。
5. 按“冲突处理原则”解决冲突；核心代码优先采用上游实现，本地功能只补差异。
6. 检查 GUI 入口、`ROOT`/`VOLUME`、请求客户端、下载客户端和配置读写是否连通。
7. 执行静态验证和现有测试：

   ```text
   .venv\Scripts\python.exe -m compileall -q source tests main.py
   .venv\Scripts\python.exe -m unittest discover -s tests -v
   git diff --check
   ```

8. 未收到“11”“构建”或“打包”前，不执行正式 cx_Freeze 构建，也不启动 EXE。
9. 若用户要求构建，再按 `AGENTS.md` 的完整目录构建、版本验证、Volume 校验和部署流程执行。

## 本次回补结果

- 已在官方 2.8 提交 `47840a1` 基础上重新回补本地修改。
- 上游 GUI 页面已纳入当前分支。
- 本地 PNG 单文件回退、失败诊断、读取失败重试、TUI 失败链接复制和记录清空功能已保留。
- 已通过 Python 编译检查。
- 已通过现有 14 个单元测试。
- 尚未构建最终 Release，也未启动软件；这是遵循项目规则的有意状态。
