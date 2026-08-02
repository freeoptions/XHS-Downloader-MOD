# XHS-Downloader-MOD 项目专属规则

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
