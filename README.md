# tgcloud

Opensourсe Telegram based cloud storage
![Diagram](/img/ProjectDiagram.png)
## Project structure:
**tgcloud:** linux based docker container
* **redis** - updates, rpc, communication
* **tfs:** FUSE based VFS module
  * [python-fuse](https://github.com/SlavikMIPT/tfs) - interface to linux kernel FS
  * redis storage - FS struct, meta, telegram file_id,settings
  * rq communication interface
  * docker
* **file_telegram_rxtx** - telegram read/write driver
  * [telethon(sync)](https://github.com/SlavikMIPT/Telethon) by [@Lonami](https://github.com/Lonami) - telegram access, multithreaded downloading/uploading
    * improved and tested by [@SlavikMIPT](https://github.com/SlavikMIPT) - load speed 240Mb/s 
  * rq communication interface
  * docker
* **polling daemon**
  * [telethon(asyncio)](https://github.com/SlavikMIPT/Telethon) - updates from telegram, synchronization, hashtags
  * rq communication interface
  * docker
* **client**
  * telegram authorization interface
  * [filebrowser](https://github.com/SlavikMIPT/filebrowser) - opensource golang filebrowser
  * windows service
  * telegram desktop client with filebrowser
  * settings, statistics, monitoring...
  * rq communication interface
  * docker

You are welcome to collaborate - contact 
Telegram: [@SlavikMIPT](t.me/SlavikMIPT)
