# XHS-Downloader-MOD 项目专属规则

本项目继承 Codex 已加载的全局 `AGENTS.md`（本机：`C:\Users\freez\.codex\AGENTS.md`）；以下保留项目专属规则。

本文件仅适用于 `XHS-Downloader-MOD` 项目，并覆盖通用规则中“只交付单个 EXE”的要求。其他项目继续遵循各自规则或通用的单 EXE 构建规则。

## 构建授权

- 未经用户单独发送“11”“构建”或“打包”，不得主动构建。
- 默认只进行正式 Release 构建，不生成 Debug 产物。
- 不生成 `setup.exe`、MSI、NSIS 或其他安装包，除非用户明确要求。

## 官方构建方式

- 必须遵循作者官方的 cx_Freeze 完整目录构建方式，禁止改用 Nuitka onefile、PyInstaller onefile 或其他单文件打包方式。
- 优先执行作者 workflow 使用的命令：

  ```powershell
  uv run python setup.py build_exe --build-exe dist/XHS-Downloader
  ```

- 如果本机没有可用的 `uv` 命令，但项目 `.venv` 已安装完整依赖和 cx_Freeze，可以执行等价命令：

  ```powershell
  .\.venv\Scripts\python.exe setup.py build_exe --build-exe dist/XHS-Downloader
  ```

- 最终构建产物必须是完整的 `dist\XHS-Downloader` 目录，而不是孤立的 EXE。

## 产物结构与验证

- 必须保留程序运行所需的完整目录结构，包括：
  - `XHS-Downloader-MOD.exe`
  - `lib`
  - `locale`
  - `static`
  - `share`（构建产物存在时）
  - cx_Freeze 生成的 DLL 和其他运行时文件
- 构建完成后必须运行以下命令验证：

  ```powershell
  .\dist\XHS-Downloader\XHS-Downloader-MOD.exe --version
  ```

- 版本命令必须正常退出，并检查 EXE、`lib`、`locale`、`static` 均存在。
- 源码测试存在时，构建前或构建后应运行现有测试；测试失败时不得部署。

## 部署规则

- 最终完整目录部署到：

  ```text
  D:\@Software\XHS-Downloader-MOD
  ```

- 禁止只复制 `XHS-Downloader-MOD.exe`；必须部署完整的 cx_Freeze 目录。
- 部署前必须确认软件进程已经退出。
- 必须保留当前安装目录中的 `Volume`，包括配置、下载记录、映射数据和日志。
- 新版本部署前，可以在同盘创建临时目录，将完整构建产物复制进去并合并旧版 `Volume`；临时目录使用固定的部署临时名称，不使用“待手动删除”命名。
- 临时版本必须通过 `--version` 和配置读取验证后，才能覆盖或替换正式目录。
- 允许直接覆盖更新 `D:\@Software\XHS-Downloader-MOD`。为避免半成品，可短暂把旧目录改名为固定的部署临时目录；部署成功后必须自动清理，部署失败则立即回滚。
- 禁止生成或遗留任何 `XHS-Downloader-MOD_待手动删除_*` 目录，不把清理工作留给用户。
- 构建目录也直接更新或使用临时目录替换；成功后自动清理旧构建临时目录，不保留历史构建副本。
- 部署后必须再次运行正式目录中的 EXE `--version`，并核对 `Volume\settings.json`、`ExploreID.db`、`MappingData.db` 等关键文件与部署前一致。

## 当前格式要求

- 默认图片下载格式为 `PNG`。
- 正常下载不得使用全局 AUTO。
- 只有某一张图片的 PNG 转换地址在常规重试后仍明确失败时，才允许仅该失败图片降级为 AUTO；不得修改全局 PNG 配置，也不得影响其他作品。

## 构建总结

每次构建完成后必须说明：

- 使用的具体构建命令；
- 最终目录、文件数量和占用空间；
- 版本验证与测试结果；
- `Volume` 数据是否完整保留；
- 部署临时目录是否已经自动清理，且没有遗留“待手动删除”目录。

## 本地纯自用界面规则

- 本项目是个人本地使用版。GUI、TUI 和用户脚本不得保留对本地使用没有帮助的免责声明、开源协议展示、项目仓库入口、作者 Star/赞助、Discord/其他项目、版本更新推广等用户可见文案或入口。
- 引入上游新版本时，只回补功能主体；上游附带的上述宣传内容不回补。
- 不删除下载、解析、任务队列、历史、日志、剪贴板、设置等实际功能。
- 法律许可、依赖声明和构建所需的机器可读元数据默认保留，不渲染到用户界面；除非用户明确要求，不为了清理界面而破坏许可证或依赖信息。
- 用户脚本不再配置上游自动更新、主页和反馈入口；脚本说明只保留功能和使用方法。

## MOD 功能经验与回补规则

- 上游同步以 `upstream/master` 的最新代码为基线，在独立的 `codex/` 分支回补本地修改；保留原有 `master`，不要直接覆盖用户分支。详细的基线、提交和回补清单维护在 `MOD_BACKPORTS.md`。
- GUI 资源根目录和用户数据目录分离：程序资源使用 `ROOT`，配置、日志、数据库和下载数据使用 `VOLUME`；源码运行和 cx_Freeze 完整目录运行都必须成立。
- 默认图片格式固定为 PNG，不使用全局 AUTO。只有单张图片的 PNG 转换地址在常规重试后明确失败时，该图片才允许降级为 AUTO，不能影响其他作品或全局设置。
- 网络请求和实际下载分别保留代理、请求头和 Referer 处理；下载链路使用 `curl_cffi` 的浏览器指纹模拟时，不能丢失既有的 impersonate 配置。
- 下载失败要保留可诊断信息，写入 `Volume/Logs/request_failures.log`；记录前清理 URL 查询参数中的令牌等敏感信息。
- 重试队列只收集适合重试的读取失败；404 等明确不存在的资源不进入重试。长延迟任务要保留状态、失败 URL 和进度，TUI 提供失败链接复制能力。
- GUI 2.8 的任务创建、任务队列、进度、历史、日志、设置和剪贴板流程是核心结构；后续回补时优先调用上游对应实现，避免重新复制旧版页面。
- 保留并验证这些已回补能力：视频封面下载、动态图片地址、视频直链、RedNote 域名、指定图片序号、用户脚本任务推送、脚本服务器来源校验、缓冲下载、Range 和进度处理。
- `IDRecorder` 提供记录清理和数量统计，TUI 支持清空记录；配置升级必须兼容旧字段并清理已经废弃的免责声明标记。
- 修改后默认执行静态验证：`.venv\Scripts\python.exe -m compileall -q source tests main.py`、`.venv\Scripts\python.exe -m unittest discover -s tests -v`、`node --check static\GUI\app.js`、`node --check static\XHS-Downloader.js` 和 `git diff --check`。
- 未收到“11”“构建”或“打包”前，不启动 GUI/EXE，不启动开发服务器，也不执行最终 Release 构建；UI 修改先做静态检查，待用户确认后再构建。
