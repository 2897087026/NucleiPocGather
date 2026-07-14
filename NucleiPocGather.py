import glob
import os
import shutil
import subprocess
import time
import requests
from collections import defaultdict
from tqdm import tqdm
import concurrent.futures
import WirteREADME
from DeWeight import deWeight
from utils import streaming_md5, retry, git_run, shell_run


class RepoManager:
    def __init__(self, repo_file, clone_dir):
        self.repo_file = repo_file  # 包含仓库URL的文件路径
        self.clone_dir = clone_dir  # 克隆目标目录

    def ensure_clone_directory(self):
        try:
            # 确保克隆目录存在
            os.makedirs(self.clone_dir, exist_ok=True)
        except OSError as e:
            print(f"[x] 创建目录 {self.clone_dir} 时出错: {e}")
            return False
        return True

    def read_repo_file(self):
        try:
            # 读取包含仓库URL的文件
            with open(self.repo_file, 'r') as file:
                urls = list(set(line.strip() for line in file if line.strip()))
            return urls
        except FileNotFoundError:
            print(f"[x] 文件 {self.repo_file} 未找到。")
        except Exception as e:
            print(f"[x] 读取文件 {self.repo_file} 时出错: {e}")
        return []

    def process_repos(self, urls):
        for url in urls:
            try:
                parts = url.split('/')
                if len(parts) >= 2:
                    owner, repo_name = parts[-2], parts[-1]
                    target_dir = os.path.join(self.clone_dir, f"{owner}/{repo_name}".lower())
                else:
                    print(f"[x] 无效的URL格式: {url}")
                    continue

                if os.path.isdir(target_dir):
                    self.update_repo(repo_name, target_dir)
                else:
                    self.clone_repo(url, repo_name, target_dir)
            except Exception as e:
                print(f"[x] 处理仓库 {url} 时出错: {e}")

    def update_repo(self, repo_name, target_dir):
        print(f"[+] 更新 {repo_name} 在 {target_dir}")
        try:
            git_run(["-C", target_dir, "pull", "--rebase"], timeout=120)
        except subprocess.TimeoutExpired:
            print(f"[x] 更新仓库 {repo_name} 超时")
        except subprocess.CalledProcessError as e:
            print(f"[x] 更新仓库 {repo_name} 时出错: {e}")

    def clone_repo(self, url, repo_name, target_dir):
        print(f"[+] 克隆 {repo_name} 到 {target_dir}")
        try:
            git_run(["clone", "--depth", "1", "--single-branch", url, target_dir], timeout=300)
        except subprocess.TimeoutExpired:
            print(f"[x] 克隆仓库 {repo_name} 超时")
        except subprocess.CalledProcessError as e:
            print(f"[x] 克隆仓库 {repo_name} 时出错: {e}")

    def run(self):
        if not self.ensure_clone_directory():
            return
        urls = self.read_repo_file()
        self.process_repos(urls)


class NucleiDownloader:
    def __init__(self, repo_owner, repo_name):
        self.repo_owner = repo_owner  # 仓库拥有者
        self.repo_name = repo_name  # 仓库名称

    @retry(max_retries=3, delay=3, exceptions=(requests.RequestException,))
    def get_latest_release(self):
        url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/releases/latest"
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return response.json()

    @retry(max_retries=3, delay=3, exceptions=(requests.RequestException,))
    def download_file(self, url, dest):
        response = requests.get(url, stream=True, timeout=60)
        response.raise_for_status()
        with open(dest, 'wb') as f:
            for chunk in response.iter_content(chunk_size=65536):
                f.write(chunk)

    def find_download_url(self, assets, platform='linux', architecture='amd64', file_extension='.zip'):
        for asset in assets:
            if platform in asset['name'] and architecture in asset['name'] and asset['name'].endswith(file_extension):
                return asset['browser_download_url']
        return None

    def download_latest_release(self, dest_file):
        release = self.get_latest_release()
        assets = release['assets']

        download_url = self.find_download_url(assets)
        if not download_url:
            raise Exception("[x] 未找到适用于Linux amd64的ZIP文件")

        print(f"[+] 从 {download_url} 下载")
        self.download_file(download_url, dest_file)
        print("[+] 已下载Nuclei ZIP文件")


class POCValidator:
    def __init__(self, poc_dir, nuclei_executable="./nuclei"):
        self.poc_dir = poc_dir  # POC文件目录
        self.nuclei_executable = nuclei_executable  # Nuclei可执行文件路径

    def get_yaml_files(self):
        """递归获取指定目录下的所有 YAML 文件."""
        return glob.glob(os.path.join(self.poc_dir, "**/*.yaml"), recursive=True) +                glob.glob(os.path.join(self.poc_dir, "**/*.yml"), recursive=True)

    def validate_poc(self, file_path):
        """验证POC文件格式，使用 subprocess."""
        try:
            result = subprocess.run(
                [self.nuclei_executable, "-t", file_path, "-silent"],
                capture_output=True, text=True, timeout=60
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def process_files(self):
        yaml_files = self.get_yaml_files()
        for file_path in yaml_files:
            print(f"[+] 检查POC {file_path} 中...")

            if self.validate_poc(file_path):
                print(f"[+] {file_path}格式有效")
            else:
                print(f"[x] {file_path}格式无效，已删除")
                os.remove(file_path)


class POCOrganizer:
    def __init__(self, community_path, source_of_truth, output_path, category_map):
        self.community_path = community_path  # 社区模板路径
        self.source_of_truth = source_of_truth  # 核心模板路径
        self.output_path = output_path  # 输出路径
        self.category_map = category_map  # 分类映射
        self.category_counts = {}  # 分类计数
        self.file_hashes = {}  # 文件哈希值

    def get_all_yaml_files(self, dir_path):
        all_yaml_files = {}
        for dirpath, dirs, files in os.walk(dir_path):
            # 排除特定目录
            dirs[:] = [d for d in dirs if d != ".git" and d != "projectdiscovery__nuclei-templates"]
            for filename in files:
                if filename.endswith(".yml") or filename.endswith(".yaml"):
                    all_yaml_files[filename] = os.path.join(dirpath, filename)
        return all_yaml_files

    def categorize_file(self, file_name):
        # 根据文件名进行分类
        categories = []
        for category, keywords in self.category_map.items():
            if any(keyword in file_name.lower() for keyword in keywords):
                categories.append(category)
        return categories if categories else ["other"]

    @staticmethod
    def file_hash(file_path):
        """计算文件哈希值（流式读取）. """
        return streaming_md5(file_path)

    def copy_file_to_categories(self, file_path, categories, file_hash_value):
        # 复制文件到相应分类目录
        for category in categories:
            target_dir = os.path.join(self.output_path, category)
            os.makedirs(target_dir, exist_ok=True)

            if file_hash_value not in self.file_hashes.get(category, set()):
                shutil.copy(file_path, os.path.join(target_dir, os.path.basename(file_path)))
                self.category_counts[category] = self.category_counts.get(category, 0) + 1
                self.file_hashes.setdefault(category, set()).add(file_hash_value)

    def get_file_size(self, file_path):
        return os.path.getsize(file_path)

    def process_files(self):
        community = self.get_all_yaml_files(self.community_path)
        nuclei_templates = self.get_all_yaml_files(self.source_of_truth)

        common_templates = set(community.keys()) & set(nuclei_templates.keys())

        for template, community_file in community.items():
            if template in common_templates and self.get_file_size(community_file) == self.get_file_size(
                    nuclei_templates[template]):
                os.remove(community_file)
                continue

            categories = self.categorize_file(os.path.basename(community_file))
            file_hash_value = self.file_hash(community_file)
            self.copy_file_to_categories(community_file, categories, file_hash_value)

    def print_summary(self):
        print("[+] 各类文件数量:")
        total_count = 0
        for category, count in self.category_counts.items():
            total_count += count
            print(f"[+] {category}: {count}")
        print(f"[+] all: {total_count}")


class DuplicateFileHandler:
    def __init__(self, base_dir):
        self.base_dir = base_dir  # 基目录
        self.file_hashes = defaultdict(list)  # 文件哈希值
        self.duplicate_files = {}  # 重复文件

    @staticmethod
    def calculate_file_hash(file_path):
        """计算文件的 MD5 哈希值（流式读取）. """
        return streaming_md5(file_path)

    def get_yaml_files(self):
        """递归遍历给定目录下的所有 .yaml 文件，并返回文件路径列表."""
        file_paths = []
        for root, _, files in os.walk(self.base_dir):
            for filename in files:
                if filename.endswith(".yaml") or filename.endswith(".yml"):
                    file_path = os.path.join(root, filename)
                    file_paths.append(file_path)
        return file_paths

    def find_duplicate_files(self, file_paths):
        """找到内容相同的文件，并返回一个包含重复文件的字典."""
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = {executor.submit(self.calculate_file_hash, file_path): file_path for file_path in file_paths}
            for future in tqdm(concurrent.futures.as_completed(futures), total=len(file_paths), desc="计算文件哈希值"):
                file_path = futures[future]
                file_hash = future.result()
                self.file_hashes[file_hash].append(file_path)

        # 找到内容相同的文件
        self.duplicate_files = {hash_value: files for hash_value, files in self.file_hashes.items() if len(files) > 1}

    def print_and_remove_duplicate_files(self):
        """打印内容相同的文件路径，并删除多余的文件."""
        total_duplicates = 0

        for hash_value, files in self.duplicate_files.items():
            print(f"[+] 哈希值为 {hash_value} 的文件内容相同:")
            for file in files:
                print(f"  {file}")

            # 删除多余的文件，只保留一个
            for file_to_remove in files[1:]:
                os.remove(file_to_remove)
                print(f"[+] 删除文件: {file_to_remove}")
                total_duplicates += 1

        print(f"[+] 总共有 {len(self.duplicate_files)} 组重复的文件.")
        print(f"[+] 总共删除了 {total_duplicates} 个重复文件.")

    def process(self):
        file_paths = self.get_yaml_files()
        print(f"[+] 找到 {len(file_paths)} 个 YAML 文件.")

        self.find_duplicate_files(file_paths)
        self.print_and_remove_duplicate_files()


def pocfenlei():
    category_map = {
        "wordpress": ["wp", "wordpress"],
        "xss": ["xss"],
        "sql_injection": ["sqli", "sql_injection", "sql"],
        "local_file_inclusion": ["lfi", "local_file_inclusion"],
        "remote_code_execution": ["rce"],
        "cross_site_request_forgery": ["csrf"],
        "xml_external_entity": ["xxe"],
        "cve": ["cve"],
        "cnvd": ["cnvd"],
        "cnnvd": ["cnnvd"],
        "open_redirect": ["redirect", "open_redirect"],
        "ssrf": ["ssrf", "server_side_request_forgery"],
        "subdomain_takeover": ["subdomain_takeover", "takeover"],
        "template_injection": ["template_injection", "ssti"],
        "crlf_injection": ["crlf_injection", "crlf"],
        "directory_listing": ["directory_listing", "traversal"],
        "exposed": ["exposed", "disclosure", "sensitive", "exposure"],
        "adobe": ["adobe", "aem"],
        "coldfusion": ["coldfusion", "cfm"],
        "drupal": ["drupal"],
        "joomla": ["joomla"],
        "magento": ["magento"],
        "php": ["php"],
        "airflow": ["airflow"],
        "aws": ["aws", "amazon", "ec2", "s3", "lambda", "cloudfront"],
        "apache": ["apache"],
        "cpanel": ["cpanel"],
        "docker": ["docker", "container", "kubernetes"],
        "git": ["git"],
        "jenkins": ["jenkins"],
        "cisco": ["cisco"],
        "api": ["api"],
        "upload": ["upload"],
        "sensitive": ["sensitive"],
        "debug": ["debug"],
        "backup": ["backup"],
        "auth": ["auth", "login", "signin", "sign_in", "sign-in", "oauth", "sso", "register", "signup", "sign_up",
                 "sign-up", "password", "pwd", "passwd", "secret", "token", "credential", "cred", "jwt", "cookie",
                 "session", "remember", "keycloak", "key"],
        "atlassian": ["atlassian", "jira", "confluence", "bitbucket", "bamboo"],
        "config": ["config", "conf", "configuration"],
        "mysql": ["mysql", "mariadb"],
        "sql": ["sql", "database", "db"],
        "default": ["default"],
        "detect": ["detect"],
        "extract": ["extract"],
        "fuzz": ["fuzz"],
        "graphql": ["graphql"],
        "http": ["http"],
        "social": ["social", "social_media", "facebook", "twitter", "instagram", "linkedin"],
        "favicon": ["favicon"],
        "python": ["python", "flask", "django"],
        "ftp": ["ftp"],
        "gcloud": ["gcloud", "google_cloud", "gcp"],
        "google": ["google"],
        "graphite": ["graphite"],
        "header": ["header"],
        "injection": ["injection"],
        "ibm": ["ibm"],
        "search": ["search"],
        "ldap": ["ldap"],
        "microsoft": ["microsoft", "ms"],
        "mongodb": ["mongodb", "mongo"],
        "netlify": ["netlify"],
        "oracle": ["oracle"],
        "java": ["java", "jsp", "jsf", "j2ee", "j2se", "j2me", "jvm", "jre", "jdk", "jboss", "tomcat", "glassfish",
                 "wildfly", "jetty", "websphere", "weblogic", "spring", "struts", "hibernate", "mybatis", "shiro"],
        "javascript": ["javascript", "js"],
        "elk": ["elk", "elasticsearch", "kibana", "logstash"],
        "kafka": ["kafka"],
        "kong": ["kong"],
        "laravel": ["laravel"],
        "nginx": ["nginx"],
        "nodejs": ["nodejs", "node", "express", "npm"],
        "perl": ["perl"],
        "postgres": ["postgres", "postgresql"],
        "rabbitmq": ["rabbitmq"],
        "redis": ["redis"],
        "ruby": ["ruby", "rails"],
        "samba": ["samba"],
        "sharepoint": ["sharepoint"],
        "smtp": ["smtp"],
        "sap": ["sap"],
        "shopify": ["shopify"],
        "ssh": ["ssh"],
        "vmware": ["vmware"],
        "web": ["web"],
    }

    community_path = "clone-templates"
    source_of_truth = "clone-templates/projectdiscovery/nuclei-templates"
    output_path = "poc"

    organizer = POCOrganizer(community_path, source_of_truth, output_path, category_map)
    organizer.process_files()
    organizer.print_summary()

    shutil.rmtree('clone-templates', ignore_errors=True)


def getPocName():
    yaml_files = sorted(glob.glob("**/*.yaml", recursive=True) + glob.glob("**/*.yml", recursive=True))
    with open("poc.txt", "w") as f:
        for fp in yaml_files:
            f.write("./" + fp + "\n")
    print(f"[+] 所有的 POC 名称已写入文件 poc.txt")


def run():
    # 1. 读取文件中的poc库地址，并下载
    repo_file = "repo.txt"
    clone_dir = "clone-templates"
    manager = RepoManager(repo_file, clone_dir)
    manager.run()

    # 2. 下载 nuclei
    downloader = NucleiDownloader(repo_owner="projectdiscovery", repo_name="nuclei")
    downloader.download_latest_release(dest_file="nuclei.zip")
    shell_run("unzip -o nuclei.zip nuclei", timeout=30)
    shell_run("rm -rf nuclei.zip", timeout=10)

    # 3. 检查 POC 能否使用，不能使用的进行删除
    poc_validator = POCValidator(poc_dir="clone-templates")
    poc_validator.process_files()

    # 4. 对所有的poc进行分类
    pocfenlei()

    # 5. 对已有的poc进行 hash 计算去除重复的 poc
    base_dir = os.path.join(os.getcwd(), 'poc')
    handler = DuplicateFileHandler(base_dir)
    handler.process()

    # 6. 获取所有的 POC 名字并写入文件中
    getPocName()

    # 7.对当前poc进行进一步的去重
    deWeight()

    # 8.更新 README 文件
    WirteREADME.write_readme()


if __name__ == '__main__':
    run()
