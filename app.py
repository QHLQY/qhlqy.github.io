"""基于 Flask 的个人主页应用。

启动时会读取 config.json（缺失则回退到 default/default_config.json 或内置默认配置），
再通过 GitHub API 获取用户信息并渲染 templates/index.html。
"""

import json
import os
import shutil
import time
from datetime import datetime

import markdown
import requests
from flask import Flask, abort, jsonify, render_template, send_from_directory

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, 'config.json')
DEFAULT_CONFIG_PATH = os.path.join(BASE_DIR, 'default', 'default_config.json')

DEFAULT_CONFIG = {
    "github_url": "https://github.com/example",
    "dark_mode": "auto",
    "name": "Example User",
    "bio": "Python Developer",
    "introduction_file": "Introduction.md",
    "github_token": "",
    "theme": {
        "primary_color": "#6a11cb",
        "secondary_color": "#2575fc",
        "dark_primary_color": "#a855f7",
        "dark_secondary_color": "#60a5fa",
    },
    "background": {
        "image": "background.jpg",
        "blur": 8,
        "overlay_opacity": 0.6,
        "overlay_color": "#f3f4f6",
        "dark_overlay_color": "#121212",
    },
    "contact": {
        "github": "",
        "email": "",
        "qq": "",
        "wechat": "",
        "bilibili": "",
        "douyin": "",
        "xiaohongshu": "",
    },
}


def _deep_merge(base, override):
    """递归合并配置，override 中的值优先，缺失的键使用 base 的值。"""
    result = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config():
    """读取配置文件，缺失时依次回退到默认配置文件与内置默认值。"""
    if not os.path.exists(CONFIG_PATH) and os.path.exists(DEFAULT_CONFIG_PATH):
        print(f"config.json 不存在，从 {DEFAULT_CONFIG_PATH} 复制默认配置")
        shutil.copy2(DEFAULT_CONFIG_PATH, CONFIG_PATH)

        default_background = DEFAULT_CONFIG['background']['image']
        if not os.path.exists(os.path.join(BASE_DIR, default_background)):
            source = os.path.join(BASE_DIR, 'default', default_background)
            if os.path.exists(source):
                shutil.copy2(source, os.path.join(BASE_DIR, default_background))

    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                user_config = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"读取 config.json 失败，使用默认配置: {exc}")
            user_config = {}
    else:
        print("未找到 config.json，使用内置默认配置")
        user_config = {}

    merged = _deep_merge(DEFAULT_CONFIG, user_config)

    # 确保背景图存在，缺失时尝试从 default/ 复制
    background = merged['background']['image']
    background_abs = os.path.join(BASE_DIR, background)
    if not os.path.exists(background_abs):
        fallback = os.path.join(BASE_DIR, 'default', os.path.basename(background))
        if os.path.exists(fallback):
            shutil.copy2(fallback, background_abs)
            print(f"{background} 不存在，已从 default/ 复制")

    return merged


config = load_config()

app = Flask(__name__)
app.config['theme'] = config['theme']
app.config['dark_mode'] = config['dark_mode']

GITHUB_API = 'https://api.github.com'
REQUEST_TIMEOUT = 8


def _github_token():
    """按 环境变量 -> github_token.txt -> config.json 的顺序读取令牌。"""
    token = os.environ.get('GITHUB_TOKEN', '').strip()
    if token:
        return token

    token_file = os.path.join(BASE_DIR, 'github_token.txt')
    if os.path.exists(token_file):
        try:
            with open(token_file, 'r', encoding='utf-8') as f:
                return f.read().strip().strip('"').strip("'")
        except OSError as exc:
            print(f"读取 github_token.txt 失败: {exc}")

    return str(config.get('github_token') or '').strip()


class _FailedResponse:
    """请求异常时的占位响应，避免调用方处理 None。"""

    status_code = 0
    text = ''

    def json(self):
        return {}


def github_request(url, timeout=REQUEST_TIMEOUT):
    """带认证与错误处理的 GitHub API 请求。"""
    headers = {
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'qhlqy-homepage',
    }
    token = _github_token()
    if token:
        headers['Authorization'] = f'Bearer {token}'

    # 默认校验 HTTPS 证书；本地证书异常时可设置 GITHUB_INSECURE=1 临时关闭校验
    verify = os.environ.get('GITHUB_INSECURE') != '1'

    try:
        response = requests.get(url, headers=headers, timeout=timeout, verify=verify)
    except requests.RequestException as exc:
        print(f"GitHub API 请求异常: {exc}")
        return _FailedResponse()

    if response.status_code == 403 and 'rate limit' in response.text.lower():
        print("GitHub API 速率限制已达，建议配置 GITHUB_TOKEN 环境变量")

    return response


def get_username():
    """从配置的 GitHub 主页地址中提取用户名。"""
    github_url = str(config.get('github_url', '')).rstrip('/')
    username = github_url.rsplit('/', 1)[-1]
    if username.endswith('.git'):
        username = username[:-4]
    return username or 'example'


def get_github_user_info():
    """获取用户信息、仓库、活动与技术栈数据，失败时返回兜底数据。"""
    if os.environ.get('HOMEPAGE_OFFLINE') == '1':
        print("HOMEPAGE_OFFLINE=1，跳过 GitHub API 请求")
        return _fallback_user_info()

    username = get_username()
    print(f"开始获取 GitHub 用户信息: {username}")

    try:
        user_response = github_request(f'{GITHUB_API}/users/{username}')
        if user_response.status_code != 200:
            print(f"获取用户信息失败，状态码: {user_response.status_code}")
            return _fallback_user_info()

        user_data = user_response.json()

        repos_response = github_request(
            f'{GITHUB_API}/users/{username}/repos?sort=pushed&per_page=100'
        )
        if repos_response.status_code != 200:
            print(f"获取仓库列表失败，状态码: {repos_response.status_code}")
            return _fallback_user_info()

        repos = repos_response.json()
        # /users/{user}/repos 最多返回 100 个，总数优先使用用户资料中的 public_repos
        total_repos = user_data.get('public_repos', len(repos))
        total_stars = sum(repo.get('stargazers_count', 0) for repo in repos)
        recent_repos = sorted(
            repos, key=lambda repo: repo.get('pushed_at', ''), reverse=True
        )[:5]

        return {
            "avatar_url": user_data.get('avatar_url'),
            "name": user_data.get('name') or user_data.get('login') or username,
            "bio": config.get('bio', ''),
            "total_repos": total_repos,
            "total_stars": total_stars,
            "readme_content": get_readme_content(username),
            "recent_repos": recent_repos,
            "activity_data": get_github_activity_data(username),
            "tech_stack": analyze_tech_stack(repos),
        }
    except Exception as exc:  # noqa: BLE001 - 外部服务异常不应导致页面 500
        print(f"GitHub API 调用异常: {type(exc).__name__}: {exc}")
        return _fallback_user_info()


def _fallback_user_info():
    return {
        "avatar_url": "https://avatars.githubusercontent.com/u/1000000?v=4",
        "name": config.get('name', 'Example User'),
        "bio": config.get('bio', ''),
        "total_repos": 0,
        "total_stars": 0,
        "readme_content": get_local_readme(),
        "recent_repos": [],
        "activity_data": [65, 59, 80, 81, 56, 55, 70, 65, 85, 75, 60, 75],
        "tech_stack": [
            {"name": "Python", "color": "#6a11cb"},
            {"name": "JavaScript", "color": "#2575fc"},
            {"name": "HTML/CSS", "color": "#560bad"},
            {"name": "Flask", "color": "#1e40af"},
        ],
    }


def get_github_activity_data(username):
    """统计过去 12 个月的提交活动（GitHub Events 最多保留 90 天）。"""
    now = datetime.now()
    activity_counts = [0] * 12

    def get_month_index(dt):
        diff = (now.year - dt.year) * 12 + (now.month - dt.month)
        return 11 - diff if 0 <= diff < 12 else None

    try:
        seen_events = set()
        for page in range(1, 4):
            response = github_request(
                f'{GITHUB_API}/users/{username}/events/public'
                f'?per_page=100&page={page}'
            )
            if response.status_code != 200:
                break

            events = response.json()
            if not events:
                break

            for event in events:
                event_id = event.get('id')
                if event_id in seen_events:
                    continue
                seen_events.add(event_id)

                if event.get('type') != 'PushEvent':
                    continue

                created_at = event.get('created_at', '')
                try:
                    created = datetime.strptime(created_at, '%Y-%m-%dT%H:%M:%SZ')
                except ValueError:
                    continue

                index = get_month_index(created)
                if index is not None:
                    activity_counts[index] += event.get('payload', {}).get('size', 1)

            if len(events) < 100:
                break

        if sum(activity_counts) == 0:
            return [45, 52, 38, 65, 48, 56, 70, 80, 85, 75, 60, 75]

        return activity_counts
    except Exception as exc:  # noqa: BLE001
        print(f"获取活动数据失败: {exc}")
        return [0] * 12


# 技术栈缓存（默认 1 小时）
cached_tech_stack = None
cached_timestamp = 0
CACHE_DURATION = 3600


def analyze_tech_stack(repos):
    """根据仓库语言统计生成技术栈标签，并缓存结果。"""
    global cached_tech_stack, cached_timestamp

    current_time = time.time()
    if cached_tech_stack and (current_time - cached_timestamp < CACHE_DURATION):
        return cached_tech_stack

    try:
        language_stats = {}

        # 只分析最近活跃的 10 个仓库，控制 API 调用次数
        for repo in repos[:10]:
            language = repo.get('language')
            if language:
                language_stats[language] = language_stats.get(language, 0) + 1

            if len(language_stats) < 5 and repo.get('languages_url'):
                languages_response = github_request(repo['languages_url'])
                if languages_response.status_code == 200:
                    for language, byte_count in languages_response.json().items():
                        language_stats[language] = language_stats.get(language, 0) + byte_count

        if not language_stats:
            cached_tech_stack = list(_fallback_user_info()['tech_stack'])
            cached_timestamp = time.time()
            return cached_tech_stack

        sorted_languages = sorted(
            language_stats.items(), key=lambda item: item[1], reverse=True
        )[:10]

        theme = app.config.get('theme', DEFAULT_CONFIG['theme'])
        is_dark = app.config.get('dark_mode', 'auto') == 'dark'
        if is_dark:
            base_colors = [theme['dark_primary_color'], theme['dark_secondary_color']]
        else:
            base_colors = [theme['primary_color'], theme['secondary_color']]

        def generate_harmonious_color(base_color, index, dark=False):
            hex_color = base_color.lstrip('#')
            r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
            factor = 1.0 - index * 0.15
            if factor < 0.4:
                factor = 0.4
            if dark:
                factor = min(0.9, 0.6 + index * 0.1)
            return f'#{int(r * factor):02x}{int(g * factor):02x}{int(b * factor):02x}'

        color_map = {
            'Python': generate_harmonious_color(base_colors[0], 0, is_dark),
            'JavaScript': generate_harmonious_color(base_colors[1], 0, is_dark),
            'Java': generate_harmonious_color(base_colors[0], 1, is_dark),
            'TypeScript': generate_harmonious_color(base_colors[1], 1, is_dark),
            'Go': generate_harmonious_color(base_colors[0], 2, is_dark),
            'Rust': generate_harmonious_color(base_colors[1], 2, is_dark),
            'PHP': generate_harmonious_color(base_colors[0], 3, is_dark),
            'C++': generate_harmonious_color(base_colors[1], 3, is_dark),
            'C': generate_harmonious_color(base_colors[0], 4, is_dark),
            'C#': generate_harmonious_color(base_colors[1], 4, is_dark),
            'Ruby': generate_harmonious_color(base_colors[0], 5, is_dark),
            'Swift': generate_harmonious_color(base_colors[1], 5, is_dark),
            'Kotlin': generate_harmonious_color(base_colors[0], 6, is_dark),
            'HTML': generate_harmonious_color(base_colors[1], 6, is_dark),
            'CSS': generate_harmonious_color(base_colors[0], 7, is_dark),
            'SCSS': generate_harmonious_color(base_colors[1], 7, is_dark),
            'Less': generate_harmonious_color(base_colors[0], 8, is_dark),
            'Flask': generate_harmonious_color(base_colors[1], 8, is_dark),
            'Django': generate_harmonious_color(base_colors[0], 9, is_dark),
            'React': generate_harmonious_color(base_colors[1], 9, is_dark),
            'Vue': generate_harmonious_color(base_colors[0], 10, is_dark),
            'Angular': generate_harmonious_color(base_colors[1], 10, is_dark),
            'Node.js': generate_harmonious_color(base_colors[0], 11, is_dark),
        }

        tech_stack = []
        html_css_added = False

        for language, _ in sorted_languages:
            if language in ('HTML', 'CSS', 'SCSS', 'Less', 'Sass'):
                if not html_css_added:
                    tech_stack.append({
                        "name": "HTML/CSS",
                        "color": color_map.get('HTML', 'orange'),
                    })
                    html_css_added = True
            else:
                tech_stack.append({
                    "name": language,
                    "color": color_map.get(language, 'gray'),
                })

        tech_stack = tech_stack[:10]
        cached_tech_stack = tech_stack
        cached_timestamp = time.time()
        print(f"分析完成的技术栈: {[tech['name'] for tech in tech_stack]}")
        return tech_stack
    except Exception as exc:  # noqa: BLE001
        print(f"分析技术栈时发生异常: {exc}")
        return _fallback_user_info()['tech_stack']


def get_readme_content(username):
    """优先获取 GitHub 同名仓库的 README，失败时回退到本地介绍文件。"""
    for branch in ('main', 'master'):
        url = f'https://raw.githubusercontent.com/{username}/{username}/{branch}/README.md'
        try:
            response = requests.get(
                url,
                timeout=REQUEST_TIMEOUT,
                verify=os.environ.get('GITHUB_INSECURE') != '1',
                headers={'User-Agent': 'qhlqy-homepage'},
            )
        except requests.RequestException as exc:
            print(f"获取 README 异常: {exc}")
            continue

        if response.status_code == 200:
            return markdown.markdown(response.text)

    print("GitHub README 获取失败，使用本地介绍文件")
    return get_local_readme()


def get_local_readme():
    """读取本地 Markdown 介绍文件并转换为 HTML。"""
    introduction_file = config.get('introduction_file', 'Introduction.md')
    path = introduction_file
    if not os.path.isabs(path):
        path = os.path.join(BASE_DIR, path)

    try:
        with open(path, 'r', encoding='utf-8') as f:
            return markdown.markdown(f.read())
    except OSError:
        return "<p>这个人很懒，什么都没有留下～</p>"


@app.route('/')
def index():
    github_info = get_github_user_info()

    background_image = config.get('background', {}).get('image', 'background.jpg')
    background_exists = False
    background_path = background_image

    for path, public_path in (
        (os.path.join(BASE_DIR, background_image), background_image),
        (os.path.join(BASE_DIR, 'static', background_image), f'/static/{background_image}'),
    ):
        if os.path.exists(path):
            background_exists = True
            background_path = public_path
            break

    return render_template(
        'index.html',
        github_info=github_info,
        config=config,
        now=datetime.now(),
        background_exists=background_exists,
        background_path=background_path,
    )


@app.route('/api/config')
def get_config():
    return jsonify(config)


@app.route('/<path:filename>')
def serve_root_file(filename):
    """提供根目录下的图片、样式与脚本等静态资源。"""
    allowed_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp', '.ico', '.css', '.js'}
    if os.path.splitext(filename)[1].lower() not in allowed_extensions:
        abort(404)

    try:
        return send_from_directory(BASE_DIR, filename)
    except FileNotFoundError:
        abort(404)


if __name__ == '__main__':
    debug = os.environ.get('FLASK_DEBUG', '0') == '1'
    app.run(
        debug=debug,
        host=os.environ.get('HOST', '0.0.0.0'),
        port=int(os.environ.get('PORT', '5000')),
    )
