# tgcloud
## UNDER DEVELOPMENT
- Необходимо получить api_hash и api_id на my.telegram.org и вставить эти данные вместе с номером телефона вашего аккаунта в tg_access.py

- Установить зависимости

```sudo pip3 install -r requirements.txt```

- Создать сессию запустив из папки с проектом и введя код подтверждения

```python3.6 download_service.py```

- Установить fuse bindings

```sudo yum install python-fuse```

- Создать папку для монтирования 

```mkdir storage```

- Запустить VFS: 

с отладкой 

```python dedupfs/dedupfs.py -df --block-size 10240000 storage/```

в фоне 

```python dedupfs/dedupfs.py --block-size 10240000 storage/```

- Можно, например указать эту папку как источник для [filebrowser](https://github.com/filebrowser/filebrowser)

You are welcome to collaborate - contact 
Telegram: [@SlavikMIPT](t.me/SlavikMIPT)
Channel: [@MediaTube_stream](t.me/MediaTube_stream)
