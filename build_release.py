"""build_release.py —— 一键构建全部发布物（克隆仓库后先 pip install -r requirements.txt pyinstaller）。

产出（均在 dist/ 下）：
  dist/NewsHub.exe          免安装单文件版（仓库根目录同款）
  dist/NewsHub-Setup.exe    完整安装器（向导 /S 静默 /U 卸载，含 ICO 图标）
  dist/NewsHub/             安装目录版（安装器 payload 同源）

用法：python build_release.py
"""
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
ICO = os.path.join(ROOT, 'assets', 'NewsHub.ico')


def run(args):
    print('>>', ' '.join(args))
    r = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, shell=False)
    if r.returncode != 0:
        print(r.stdout[-2000:])
        print(r.stderr[-2000:])
        sys.exit(f'构建失败: {args[1] if len(args) > 1 else args}')


def build(name, onedir):
    args = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--windowed', '--icon', ICO, '--name', name, '--paths', 'src']
    if onedir:
        args.append('--onedir')
    else:
        args.append('--onefile')
    args.append('src/run_app.py' if name == 'NewsHub' else 'installer/installer.py')
    if name == 'NewsHub-Setup':
        args += ['--add-data', os.path.join('installer_build', 'payload') + os.pathsep + 'payload']
    run(args)


def main():
    if not os.path.isfile(ICO):
        sys.exit(f'缺少图标文件: {ICO}')
    dist = os.path.join(ROOT, 'dist')
    shutil.rmtree(dist, ignore_errors=True)
    shutil.rmtree(os.path.join(ROOT, 'installer_build'), ignore_errors=True)
    build('NewsHub', onedir=False)
    build('NewsHub', onedir=True)
    payload_src = os.path.join(dist, 'NewsHub')
    shutil.copy2(os.path.join(ROOT, 'config.template.json'), payload_src)
    shutil.copy2(ICO, os.path.join(payload_src, 'NewsHub.ico'))
    os.makedirs(os.path.join(ROOT, 'installer_build', 'payload'), exist_ok=True)
    for fn in os.listdir(payload_src):
        src = os.path.join(payload_src, fn)
        dst = os.path.join(ROOT, 'installer_build', 'payload', fn)
        (shutil.copytree if os.path.isdir(src) else shutil.copy2)(src, dst)
    build('NewsHub-Setup', onedir=False)
    print('\n构建完成：')
    for p in ['dist/NewsHub.exe', 'dist/NewsHub-Setup.exe']:
        full = os.path.join(ROOT, *p.split('/'))
        print(f'  {p}  ({os.path.getsize(full) / 1048576:.1f} MB)')
    print('  dist/NewsHub/           （安装目录版，含 NewsHub.ico）')
    root_exe = os.path.join(ROOT, 'NewsHub.exe')
    shutil.copy2(os.path.join(dist, 'NewsHub.exe'), root_exe)
    print(f'  NewsHub.exe（仓库根目录，已同步）')


if __name__ == '__main__':
    main()
