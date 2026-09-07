@echo off
chcp 65001 >nul
echo ================================================================
echo  前台测试运行：会等待微信、查找绿色按钮并点击（真实操作！）
echo    --dry-run  只检测不点击（安全，推荐先跑这个）
echo  示例: run_test.bat --dry-run
echo ================================================================
python "%~dp0wechat_autologin.py" %*
echo.
echo 退出码: %errorlevel%    （0=成功/无需操作 1=点击后未观察到登录 2=配置错误）
pause