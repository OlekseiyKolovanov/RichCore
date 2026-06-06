# Distribution and Code Protection

RichCore is packaged without raw `.py` source files in the installed app. The executable contains Python bytecode in the PyInstaller archive and the installer copies only the built app folder.

Important notes:

- Python desktop apps cannot be made impossible to reverse engineer.
- Heavy obfuscation or packers often increase antivirus false positives.
- UPX is disabled in the build to reduce false positives.
- One-folder distribution is used for the installed tool to avoid PyInstaller `_MEI...` temp cleanup warnings and to reduce suspicious one-file unpacking behavior.
- The best way to reduce antivirus complaints is to sign `RichCore_v12.exe` and `RichCore_Setup.exe` with a trusted code-signing certificate.

Recommended release flow:

1. Build with `scripts/build.ps1`.
2. Scan the output with Microsoft Defender locally.
3. Sign the EXE files if a certificate is available.
4. Upload `dist/RichCore_v12.zip` to the GitHub Release.
