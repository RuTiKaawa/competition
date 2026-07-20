学习了0-全栈的前端部署到服务器的步骤，参考课程（https://www.bilibili.com/video/BV15P7y6cEzf/?spm_id_from=333.1387.homepage.video_card.click&vd_source=c4d3cd62b92bf165e07fda940a04db2a）
 
总体思路流程：本地项目先ssh连接到github上再提交到项目库中,再把从服务器中通过ssh连接github项目库把项目部署到服务器上，然后在服务器上部署nginx,其中nginx文件夹下的nginx.conf是读取的唯一入口，在里面的http块中include sites-enabled文件导入具体网页设置；我们再进入sites-enabled文件可见在其server块内容
注：enabled文件类似于avaliable文件的快捷方式，后者类似于草稿，一般删除前者内文件去对一个服务器多网页情况下的管理，而基础文件都会保存在后者，再次调用只要在前者加入新的快捷方式即server块即可
server {
        listen 80 default_server;//默认80端口
        listen [::]:80 default_server;
        
        root /var/www/html;//root内容最为重要，其路径为导入配置的路径，即项目库路径

        index index.html index.htm index.nginx-debian.html;//按序遍历寻找文件

        server_name _;//DNS域名，不同的域名对应返回到该sever块的root配置中以此达到单服务器多网页的目的

        location / {
                 try_files $uri $uri/ =404;//找不到则返回404
        }
        }
}


//以下为本地指令
-git clone git@github.com:xxxxxx  //把github项目库放到本地(第一次访问的时候)
-cd project_name
-一系列更改
-git add .
-git commit -m "备注"
-git pull origin main             //把更改提交到github上

//以下为服务器指令
-git clone git@github.com:xxxxxx  //把github项目库放到服务器(第一次访问的时候)
在改完上文所述nginx配置文件以后先检查语法
-sudo nginx -t
若没问题则重载nginx
-sudo systemctl reload nginx
此时若打开网页可能会是404是因为nginx访问index.html文件时权限不够所以对其他用户给予对文件配置所在用户访问的权限
-sudo chmod o+x /home/admin
此时刷新网页可以发现已经成功将我们的网站部署到公网了

//以下是对项目更新所做内容
流程:本地文件修改->上传到github->服务器直接git pull即可更改完成
