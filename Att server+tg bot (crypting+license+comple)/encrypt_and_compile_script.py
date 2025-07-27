import asyncio
import aiofiles
import aiofiles.os
from pathlib import Path

async def compile_script(user_key: str):
    await aiofiles.os.makedirs('crypted_scripts', exist_ok=True)
    await aiofiles.os.makedirs('temp', exist_ok=True)
    try:
        async with aiofiles.open('in_script.py', 'r', encoding='utf-8') as f1:
            security_part = await f1.read()
            security_part = security_part.replace('HERE_USER_KEY', user_key)

        async with aiofiles.open('att_crypted.py', 'r', encoding='utf-8') as f2:
            main_part = await f2.read()

        output_path = f'crypted_scripts/{user_key}.py'

        async with aiofiles.open(output_path, 'w', encoding='utf-8') as f3:
            await f3.write(f'{security_part}\n\n{main_part}')

        print(f'[+] Successfully combined and crypted script to {output_path}')
        print(f'[!] Compiling to .exe')

        source = f'temp/{user_key}.exe'
        destination = f'crypted_scripts/{user_key}.exe'

        if await aiofiles.os.path.exists(destination):
            await aiofiles.os.remove(destination)

        process = await asyncio.create_subprocess_exec(
            *[
                "python",
                "-m", "nuitka",
                "--onefile",
                "--standalone",
                "--remove-output",
                "--output-dir=temp",
                output_path
            ],
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            return False

        if await aiofiles.os.path.exists(source):
            print(f'[+] Successfully compiled to {destination}')
            await aiofiles.os.rename(source, destination)
            return True
        else:
            print(f'[-] Cant compile to {destination}')
            return False

    except Exception as e:
        print(f"Error during compilation ({type(e)}): {str(e)}")
        return False

asyncio.run(compile_script(input('Enter user_key: ').strip()))