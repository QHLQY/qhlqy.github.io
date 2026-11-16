# -*- coding: utf-8 -*-
"""构建静态站点到 output/ 目录，供 GitHub Pages 部署使用。

用法:
    python build_static.py

环境变量:
    GITHUB_TOKEN      提高 GitHub API 速率限制（CI 中自动注入）
    HOMEPAGE_OFFLINE  设为 1 时不请求 GitHub API，使用兜底数据（便于离线调试）
"""

import importlib.util
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(HERE, 'output')
CONFIG_PATH = os.path.join(HERE, 'config.json')
DEFAULT_CONFIG_PATH = os.path.join(HERE, 'default', 'default_config.json')


def load_config():
    """读取配置；缺失时回退到 default/default_config.json。"""
    path = CONFIG_PATH if os.path.exists(CONFIG_PATH) else DEFAULT_CONFIG_PATH
    if not os.path.exists(path):
        print("警告：未找到 config.json，将使用应用内置默认配置")
        return {}

    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_app():
    """从 app.py 载入 Flask 应用实例。"""
    os.chdir(HERE)
    spec = importlib.util.spec_from_file_location('app', os.path.join(HERE, 'app.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules['app'] = module
    spec.loader.exec_module(module)
    return module


def render_site(flask_app):
    """通过 Flask 测试客户端渲染首页 HTML。"""
    with flask_app.test_client() as client:
        response = client.get('/')

    if response.status_code != 200:
        print(f"错误：首页渲染失败，状态码 {response.status_code}")
        sys.exit(1)

    return response.data


def prepare_output():
    if os.path.exists(OUTPUT_DIR):
        shutil.rmtree(OUTPUT_DIR)
    os.makedirs(OUTPUT_DIR)


def copy_assets(config):
    """复制背景图、CNAME 等静态资源到输出目录。"""
    candidates = []

    background = config.get('background', {}).get('image', 'background.jpg')
    if background:
        candidates.append(background)

    candidates.extend(['favicon.ico', 'CNAME'])

    for name in candidates:
        source = os.path.join(HERE, name)
        if os.path.exists(source):
            shutil.copy2(source, os.path.join(OUTPUT_DIR, os.path.basename(name)))
            print(f"已复制: {name}")


def main():
    config = load_config()
    module = load_app()
    flask_app = module.app

    print("正在渲染首页...")
    html = render_site(flask_app)

    prepare_output()
    with open(os.path.join(OUTPUT_DIR, 'index.html'), 'wb') as f:
        f.write(html)

    copy_assets(config)

    print("\n构建完成：output/index.html")
    print("部署方式：")
    print("  - GitHub Actions 会自动构建并发布 output/ 目录")
    print("  - 也可以把 output/ 目录直接上传到任意静态托管服务")


if __name__ == '__main__':
    main()
