from typing import List
import string
import random
from .module.command import command
from .module.port import port
from .module.ip import ip
from .module.request import request_class
import pathlib
from dataclasses import dataclass
import hashlib
import json
from functools import lru_cache
import asyncio


class docker(command, ip, port, request_class):
    def __init__(self):
        command.__init__(self)
        ip.__init__(self)
        port.__init__(self)
        self.service_cache = None
        pass

    def add_service_cache(self, classid, userid, service_name, port):
        """
        classid,useridをキーとしてdocker-compose.ymlのハッシュ値とportを保存
        """
        docker_service_provided_name = f"{classid}-{userid}-{service_name}"
        if self.service_cache is None:
            try:
                with open("service_cache.json") as f:
                    self.service_cache = json.load(f)
            except BaseException:
                self.service_cache = {}
        yml = self.select_service(service_name)
        yml_data = self.load_file(yml)
        service_hash = hashlib.sha3_512(yml_data.encode("utf-8")).hexdigest()
        self.service_cache[docker_service_provided_name] = {
            "port": int(port), "hash": service_hash}
        with open("service_cache.json", "w") as f:
            json.dump(self.service_cache, f, indent=4, sort_keys=True)

    async def get_port_from_service_cache(
            self, classid, userid, service_name) -> int:
        """
        classid,useridをキーとしてdocker-compose.ymlのハッシュ値に変更がなければ、前回の割当portを返す
        """
        docker_service_provided_name = f"{classid}-{userid}-{service_name}"
        services = await self.get_services()
        if docker_service_provided_name not in services:
            return None

        if self.service_cache is None:
            try:
                with open("service_cache.json") as f:
                    self.service_cache = json.load(f)
            except BaseException:
                self.service_cache = {}
        if docker_service_provided_name not in self.service_cache:
            return None
        yml = self.select_service(service_name)
        yml_data = self.load_file(yml)
        service_hash = hashlib.sha3_512(yml_data.encode("utf-8")).hexdigest()
        if self.service_cache[docker_service_provided_name]["hash"] == service_hash:
            """
            print(
                "問い合わせ結果=",
                await self.get_service_port(
                    classid,
                    userid,
                    service_name))
            print(
                "キャッシュ情報=",
                self.service_cache[docker_service_provided_name]["port"])
            """
            # port = self.service_cache[docker_service_provided_name]["port"]

            port = await self.get_service_port(
                classid,
                userid,
                service_name)

            return port
        else:
            return None

    def GetRandomStr(self, num) -> str:
        # 英数字をすべて取得
        dat = string.digits + string.ascii_lowercase + string.ascii_uppercase

        # 英数字からランダムに取得
        return ''.join([random.choice(dat) for i in range(num)])

    def get_yml_list(self) -> List[pathlib.PosixPath]:
        service_path = pathlib.Path("./service")
        yml_list = []
        yml_list.extend(service_path.glob('*/docker-compose.yml'))
        yml_list.extend(service_path.glob('*/docker-compose.yaml'))
        return yml_list

    def get_sh_list(self) -> List[pathlib.PosixPath]:
        service_path = pathlib.Path("./service")
        yml_list = []
        yml_list.extend(service_path.glob('*/docker-compose.sh'))
        return yml_list

    def get_yml_list_str(self) -> str:
        yml_list = self.get_yml_list()
        result = []
        for yml in yml_list:
            result.append(str(yml.parent.name))
        return result

    def select_service(self, service_name) -> pathlib.PosixPath:
        yml_list = self.get_yml_list()
        for yml in yml_list:
            if yml.parent.name == service_name:
                return yml
        return False

    def select_service_sh(self, service_name) -> pathlib.PosixPath:
        yml_list = self.get_sh_list()
        for yml in yml_list:
            if yml.parent.name == service_name:
                return yml
        return False

    def load_file(self, path: str) -> str:
        try:
            with open(path) as f:
                result = f.read()
            return result
        except BaseException:
            return False

    def write_file(self, path: str, data: str) -> bool:
        try:
            with open(path, "w") as f:
                f.write(data)
            return True
        except BaseException:
            return False

    def make_file(
            self,
            file_path: pathlib.PosixPath,
            port,
            userid,
            class_id) -> pathlib.PosixPath:
        file_data = self.load_file(file_path)
        file_data = file_data.replace("{automatic_allocation_port}", str(port))
        file_data = file_data.replace("{userid}", userid)
        file_data = file_data.replace("{classid}", class_id)
        file_data = file_data.replace("{servicename}", file_path.parent.name)
        filename = f"{self.GetRandomStr(20)}{file_path.suffix}"
        new_file_path = file_path.parent / filename
        self.write_file(new_file_path, file_data)
        return new_file_path

    async def deploy_service(self, yml_path: pathlib.PosixPath, service_name):
        cmd = f"docker stack deploy -c {yml_path.name} {service_name}"
        pwd = yml_path.parent
        result = await self.run(cmd, pwd)
        return result

    async def get_services(self):
        cmd = "docker stack ls --format '{{.Name}}'"
        pwd = "./"
        result = await self.run(cmd, pwd)
        return result.stdout.split("\n")

    async def get_service_port(self, classid, userid, service_name):
        cmd = f"docker service ls -f 'name={classid}-{userid}-{service_name}' --format '{{{{.Name}}}},{{{{.Ports}}}}'"
        pwd = "./"
        result = await self.run(cmd, pwd)
        port = None
        try:
            for line in result.stdout.split("\n"):
                try:
                    port_data = line.split(",")[1]
                    if len(port_data) != 0:
                        port = port_data[2:].split("->")[0]
                except BaseException:
                    pass
        except BaseException:
            port = 0
        return int(port)

    async def get_container_id(self, classid, userid, service_name) -> List[str]:
        cmd = f'docker ps | grep {classid} |grep {userid} | grep {service_name} | cut -d " " -f 1'
        pwd = "./"
        result = await self.run(cmd, pwd)
        result = result.stdout.split("\n")
        if result[-1] == "":
            result = result[:-1]
        return result

    async def stop_container(self, container_id):
        cmd = f"docker stop {container_id}"
        pwd = "./"
        result = await self.run(cmd, pwd)
        return result

    @dataclass
    class docker_result_class:
        result: bool
        service_list: list = ""
        ip: str = "0.0.0.0"
        port: int = 0
        message: str = ""
        stdout: str = ""
        stderr: str = ""

    @dataclass
    class docker_result_class2:
        result: bool
        service_list: list = ""
        message: str = ""
        stdout: str = ""
        stderr: str = ""

    async def stop(self, userid, classid, service_name):
        container_id_list = await self.get_container_id(
            classid, userid, service_name)
        tasks = []
        for container_id in container_id_list:
            tasks.append(self.stop_container(container_id))
        await asyncio.gather(*tasks)
        return "停止処理を行いました。再起動には30秒ほどかかるので安静にしてお待ち下さい"

    async def deploy(self, userid, classid, service_name, client_ip):

        # サービスの存在を確認
        service_path = self.select_service(service_name)
        if not service_path:
            return self.docker_result_class2(
                result=False,
                message="指定されたサービスが見つかりません。",
                service_list=self.get_yml_list_str())
        # 前回の立ち上げからサービスファイルが変更なければそのまま
        cache_port = await self.get_port_from_service_cache(
            classid, userid, service_name)

        if cache_port is not None:
            return self.docker_result_class(
                result=True,
                message="キャッシュを利用",
                ip=self.get_ip_address(client_ip)[0],
                port=cache_port,)
        # 新規or サービスファイルに変更があったとき
        _port = await self.scan_available_port(50000)
        # 事前スクリプトの存在確認
        service_sh_path = self.select_service_sh(service_name)
        if not service_sh_path:
            pass
        else:
            # 事前スクリプトの実行
            new_sh = self.make_file(service_sh_path, _port, userid, classid)
            cmd = f"/bin/bash {new_sh.name}"
            pwd = new_sh.parent
            result = await self.run(cmd, pwd)
            new_sh.unlink()

        new_yml = self.make_file(service_path, _port, userid, classid)
        docker_service_provided_name = f"{classid}-{userid}-{service_name}"
        result = await self.deploy_service(new_yml, docker_service_provided_name)
        new_yml.unlink()
        self.port_candidate.remove(_port)
        if result.returncode != 0:
            return self.docker_result_class2(
                result=False,
                message="docker 実行中にエラーが生じました",
                stdout=result.stdout,
                stderr=result.stderr)
        # 起動確認
        if await self.start_check(f"http://127.0.0.1:{_port}"):
            self.add_service_cache(classid, userid, service_name, _port)
            return self.docker_result_class(
                result=True,
                ip=self.get_ip_address(client_ip)[0],
                port=_port,)
        else:
            return self.docker_result_class2(
                result=False,
                message="起動確認のタイムアウトが発生しました。",)


if __name__ == "__main__":
    hoge = docker()
    test = hoge.get_yml_list()
    print(test)
    print(hoge.make_file(test[0], 1000, "dasd", "fgadsfa"))
