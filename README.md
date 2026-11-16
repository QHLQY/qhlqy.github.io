# qhlqy.github.io

基于 Flask 的个人主页，构建为静态站点后由 GitHub Actions 自动部署到 GitHub Pages。

- 线上地址：<https://qhlqy.是.gay>
- 仓库地址：<https://github.com/QHLQY/qhlqy.github.io>

## 功能

- GitHub 用户信息、仓库数、Star 数、最近仓库与技术栈展示
- 过去 12 个月的提交活动图表（Chart.js）
- 跟随系统的明暗主题，支持手动切换
- 背景图、主题色、社交链接均可在 `config.json` 中配置
- 通过 GitHub Actions 每天定时重建，保持数据更新

## 目录结构

```
app.py                  Flask 应用（数据获取 + 页面渲染）
build_static.py         用 Flask 测试客户端渲染静态站点到 output/
templates/index.html    页面模板
config.json             站点配置
Introduction.md         「关于我」区域内容（Markdown）
background.jpg          背景图
default/                默认配置与默认背景图
deploy.sh               本地开发/构建辅助脚本
.github/workflows/      GitHub Pages 自动部署
```

## 本地运行

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 启动开发服务器：http://localhost:5000
./deploy.sh run
```

如需提高 GitHub API 速率限制，任选一种方式配置令牌：

```bash
export GITHUB_TOKEN=ghp_xxx        # 推荐
# 或写入 github_token.txt（已被 .gitignore 忽略）
```

## 构建静态站点

```bash
./deploy.sh build
# 等价于 python build_static.py
```

构建结果位于 `output/`：

```
output/index.html
output/background.jpg
output/CNAME
```

离线调试时（不请求 GitHub API）可使用：

```bash
HOMEPAGE_OFFLINE=1 python build_static.py
```

## 配置

编辑 `config.json`：

| 字段 | 说明 |
| --- | --- |
| `github_url` | GitHub 主页地址，用于提取用户名 |
| `name` / `bio` | 显示的昵称与简介 |
| `introduction_file` | 本地介绍文件路径 |
| `dark_mode` | `auto` / `light` / `dark` |
| `theme` | 明暗模式下的主色与辅助色 |
| `background` | 背景图、模糊度、遮罩颜色与透明度 |
| `contact` | QQ、微信、Bilibili、抖音、小红书链接 |

缺少的字段会自动使用默认值（参见 `default/default_config.json`）。

## 部署

推荐使用 GitHub Actions：

1. 在 **Settings → Pages → Build and deployment** 将 **Source** 设为 **GitHub Actions**；
2. 推送代码到 `main`、手动触发，或等待每日定时任务，`.github/workflows/build-deploy.yml` 会：
   - 安装依赖；
   - 运行 `build_static.py` 生成 `output/`；
   - 将 `output/` 作为 Pages 产物发布。

如果 Pages 的 Source 是「Deploy from a branch（main / root）」，仓库根目录的 `index.html` 会作为页面直接提供；此时需要手动把 `output/index.html` 覆盖到根目录并提交，页面数据才会更新。建议切换到 GitHub Actions 以获得每日自动更新。

自定义域名通过仓库根目录的 `CNAME` 文件维护。

## 许可证

[MIT](LICENSE)
