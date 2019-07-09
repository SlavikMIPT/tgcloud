# tgcloud
## UNDER DEVELOPMENT v1.1
- `secret.py` : переименовать`secret.py.template`, вставить `api_hash` и `api_id` полученные с  https://my.telegram.org

- Установить Python2.7 и Python3.6

- Скачать исходный код
```
cd ~
git clone https://github.com/SlavikMIPT/tgcloud.git
```
- Установить зависимости

`sudo pip3 install -r requirements.txt`
- Создать сессию запустив **из папки с проектом**

`python3.6 telegram_create_session.py`

- Установить fuse bindings

`sudo yum install python-fuse`

- Создать папку для монтирования 

`mkdir storage`

- Запустить VFS **из папки с проектом**: 

с отладкой 

`python2.7 dedupfs/dedupfs.py -df --block-size 20971520 -o auto_unmount -o hard_remove storage/`

в фоне 

отредактировать `<username>` в `tgcloud.service`
```
sudo cp tgcloud.service /ect/systemd/system/
sudo systemctl enable tgcloud.service
sudo systemctl daemon-reload
sudo systemctl start tgcloud.service
sudo systemctl status tgcloud.service -l
```

Версия 1.1

Работает пободрее, но все еще сырой прототип - может падать.

Для тестов лучше использовать отдельный профиль. 

Если забанят - пишите `recover@telegram.org` - разбанят

You are welcome to collaborate - contact 
Telegram: [@SlavikMIPT](t.me/SlavikMIPT)
Channel: [@MediaTube_stream](t.me/MediaTube_stream)
