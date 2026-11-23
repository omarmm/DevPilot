#!/usr/bin/env python3
"""DevPilot — Linux development environment manager (preview)."""
from __future__ import annotations
import json, os, re, shlex, shutil, subprocess, threading, uuid
from pathlib import Path
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

APP_VERSION="0.3.5-preview"
HOME=Path.home()
APP_DIR=HOME/".config/linux-work-setup"
CONFIG_FILE=APP_DIR/"config.json"
PROFILE_DIR=APP_DIR/"git-profiles"
BACKUP_DIR=HOME/".local/share/linux-work-setup/backups"
GIT_BEGIN="# >>> Linux Work Setup managed Git profiles >>>"
GIT_END="# <<< Linux Work Setup managed Git profiles <<<"
SSH_BEGIN="# >>> Linux Work Setup managed SSH aliases >>>"
SSH_END="# <<< Linux Work Setup managed SSH aliases <<<"

GROUPS={
"Essentials":["git","curl","wget","build-essential","ca-certificates","gnupg","unzip"],
"PHP / Laravel":["php","php-cli","php-common","php-mysql","php-xml","php-curl","php-mbstring","php-zip","composer"],
"Python / FastAPI / AI":["python3","python3-pip","python3-venv","python3-dev","pipx"],
"Node.js":["nodejs","npm"],"Database clients":["mysql-client","sqlite3","postgresql-client"],
"Docker":["docker.io","docker-compose-v2"],"Utilities":["htop","tree","jq","openssh-client"]}

DATABASE_SERVERS=[
    {"id":"mysql","name":"MySQL Server","package":"mysql-server","service":"mysql","port":3306,"conflicts":["mariadb"]},
    {"id":"mariadb","name":"MariaDB Server","package":"mariadb-server","service":"mariadb","port":3306,"conflicts":["mysql"]},
    {"id":"postgresql","name":"PostgreSQL Server","package":"postgresql","service":"postgresql","port":5432,"conflicts":[]},
    {"id":"redis","name":"Redis Server","package":"redis-server","service":"redis-server","port":6379,"conflicts":[]},
]

# Official user-level installers for terminal coding agents.
AI_AGENTS=[
    {"id":"opencode","name":"OpenCode CLI","command":"opencode","install_command":"curl -fsSL https://opencode.ai/v2/install | bash","docs":"https://opencode.ai/docs/"},
    {"id":"claude","name":"Claude Code","command":"claude","install_command":"curl -fsSL https://claude.ai/install.sh | bash","docs":"https://code.claude.com/docs/en/getting-started"},
    {"id":"codex","name":"OpenAI Codex CLI","command":"codex","install_command":"curl -fsSL https://chatgpt.com/codex/install.sh | sh","docs":"https://learn.chatgpt.com/docs/cli"},
    {"id":"copilot","name":"GitHub Copilot CLI","command":"copilot","install_command":"curl -fsSL https://gh.io/copilot-install | bash","docs":"https://docs.github.com/en/copilot/how-tos/copilot-cli/set-up-copilot-cli/install-copilot-cli"},
]


def run(args, timeout=20):
    return subprocess.run(args,capture_output=True,text=True,timeout=timeout,check=False)

def atomic_write(path:Path, content:str, mode=0o600):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+".lws-tmp")
    fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,mode)
    with os.fdopen(fd,"w",encoding="utf-8") as f:
        f.write(content); f.flush(); os.fsync(f.fileno())
    os.replace(tmp,path)
    try: os.chmod(path,mode)
    except OSError: pass

class Config:
    def __init__(self):
        self.data={"schema_version":2,"settings":{"workspace_root":str(HOME/"Projects")},
                   "workspaces":[],"git_profiles":[]}
        if CONFIG_FILE.exists():
            loaded=json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            if loaded.get("schema_version") not in (1,2): raise RuntimeError("Unsupported config schema.")
            self.data.update(loaded); self.data["schema_version"]=2
            self.data.setdefault("workspaces",[]); self.data.setdefault("git_profiles",[])
            self.data.setdefault("settings",{}).setdefault("workspace_root",str(HOME/"Projects"))
    def save(self): atomic_write(CONFIG_FILE,json.dumps(self.data,indent=2,ensure_ascii=False))

class SafeConfigEditor:
    @staticmethod
    def replace_block(path, begin, end, block):
        path=Path(path); old=path.read_text(encoding="utf-8") if path.exists() else ""
        if (begin in old) != (end in old):
            raise RuntimeError(f"Conflict detected in {path}: only one managed marker exists. File left unchanged.")
        if begin in old:
            start=old.index(begin); finish=old.index(end,start)+len(end)
            updated=old[:start]+block+old[finish:]
        else:
            updated=old.rstrip()+"\n\n"+block+"\n" if old.strip() else block+"\n"
        atomic_write(path,updated,0o600 if path.name=="config" and path.parent.name==".ssh" else 0o600 if path.name==".gitconfig" else 0o644)

class Backup:
    TARGETS=[".gitconfig",".ssh/config",".bashrc",".zshrc"]
    def create(self, extra_files=()):
        dest=BACKUP_DIR/datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        dest.mkdir(parents=True,exist_ok=False)
        items=[]
        for rel in self.TARGETS+[".config/linux-work-setup/config.json"]:
            src=HOME/rel; item={"path":rel,"exists":src.is_file(),"copied":False}
            if src.is_file():
                out=dest/rel; out.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(src,out); item["copied"]=True
                item["backup_path"]=str(out.relative_to(dest))
            items.append(item)
        for index, extra in enumerate(extra_files):
            src=Path(extra).expanduser().resolve()
            item={"path":str(src),"exists":src.is_file(),"copied":False}
            if src.is_file():
                out=dest/"extra"/f"{index}-{src.name}"
                out.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,out)
                item["copied"]=True;item["backup_path"]=str(out.relative_to(dest))
            items.append(item)
        atomic_write(dest/"manifest.json",json.dumps({"items":items},indent=2))
        try:
            os.chmod(dest,0o700)
            for f in dest.rglob("*"):
                if f.is_file(): os.chmod(f,0o600)
        except OSError: pass
        return dest

def installed_state(pkg):
    q=run(["dpkg-query","-W","-f=${Status}",pkg],8)
    if q.returncode or "install ok installed" not in q.stdout:return "Not installed"
    p=run(["apt-cache","policy",pkg],8).stdout
    vals={}
    for line in p.splitlines():
        if ":" in line:
            k,v=line.strip().split(":",1); vals[k]=v.strip()
    return "Update available" if vals.get("Installed") and vals.get("Candidate") not in (None,"(none)",vals.get("Installed")) else "Installed"

def database_package_version(pkg):
    result=run(["dpkg-query","-W","-f=${Version}",pkg],8)
    if result.returncode==0 and result.stdout.strip():return result.stdout.strip()
    policy=run(["apt-cache","policy",pkg],8).stdout
    for line in policy.splitlines():
        if line.strip().startswith("Candidate:"):
            candidate=line.split(":",1)[1].strip()
            return candidate if candidate!="(none)" else "—"
    return "—"

def database_service_state(service):
    if not shutil.which("systemctl"):
        return {"unit_available":False,"active":"systemd unavailable","enabled":"—"}
    loaded=run(["systemctl","show",service,"--property=LoadState","--value"],8)
    if loaded.returncode or loaded.stdout.strip()!="loaded":
        return {"unit_available":False,"active":"unit not found","enabled":"—"}
    active=run(["systemctl","is-active",service],8)
    enabled=run(["systemctl","is-enabled",service],8)
    return {
        "unit_available":True,
        "active":active.stdout.strip() or "unknown",
        "enabled":enabled.stdout.strip() or "unknown",
    }

def parse_unmanaged_database_processes(ps_output):
    """Identify server processes not represented by DevPilot's APT/systemd records."""
    known={
        "mysqld":("MySQL-compatible server",3306),
        "mariadbd":("MariaDB server",3306),
        "postgres":("PostgreSQL server",5432),
        "redis-server":("Redis server",6379),
    }
    ignored={"bash","sh","dash","zsh","fish","grep","tail","ps","sudo","pkexec"}
    found=[]
    for line in ps_output.splitlines():
        fields=line.strip().split(None,1)
        if len(fields)!=2 or not fields[0].isdigit():continue
        pid,args=fields
        try:tokens=shlex.split(args)
        except ValueError:continue
        if not tokens:continue
        first_name=Path(tokens[0]).name.lower()
        if first_name in ignored:continue
        binary=next((token for token in tokens if Path(token).name in known),None)
        if not binary:continue
        if binary!=tokens[0] and not first_name.startswith(("ld-linux","ld-")):continue
        name,default_port=known[Path(binary).name]
        def option_value(option):
            prefix=option+"="
            for index,token in enumerate(tokens):
                if token.startswith(prefix):return token[len(prefix):]
                if token==option and index+1<len(tokens):return tokens[index+1]
            return ""
        raw_port=option_value("--port")
        try:port=int(raw_port) if raw_port else default_port
        except ValueError:port=default_port
        found.append({
            "pid":pid,"name":name,"binary":binary,"port":port,
            "datadir":option_value("--datadir"),
            "socket":option_value("--socket"),
        })
    return found


def mysql_sql_literal(value):
    """Encode a printable value as a MySQL string literal."""
    value=str(value)
    if any(ord(ch)<32 or ord(ch)==127 for ch in value):
        raise ValueError("Control characters are not allowed.")
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def build_mysql_user_sql(username, password, privilege_mode, database=""):
    """Build SQL for a new local TCP account; never alter an existing account."""
    if not re.fullmatch(r"[A-Za-z0-9_]{1,32}", username or ""):
        raise ValueError("Username must contain 1–32 letters, digits, or underscores.")
    if len(password) < 12 or len(password) > 128:
        raise ValueError("Password must be between 12 and 128 characters.")
    if privilege_mode == "admin":
        grant = "GRANT ALL PRIVILEGES ON *.* TO {account} WITH GRANT OPTION;\nGRANT CREATE USER ON *.* TO {account} WITH GRANT OPTION;"
    elif privilege_mode == "database":
        if not re.fullmatch(r"[A-Za-z0-9_]{1,64}", database or ""):
            raise ValueError("Database name must contain 1–64 letters, digits, or underscores.")
        grant = f"GRANT ALL PRIVILEGES ON `{database}`.* TO {{account}};"
    else:
        raise ValueError("Choose a supported privilege level.")
    account = mysql_sql_literal(username) + "@'127.0.0.1'"
    return (
        f"CREATE USER {account} IDENTIFIED BY {mysql_sql_literal(password)};\n"
        + grant.format(account=account)
        + "\nFLUSH PRIVILEGES;\n"
    )



def _validate_access_credentials(username,password):
    if not re.fullmatch(r"[A-Za-z0-9_]{1,32}",username or ""):
        raise ValueError("Username must contain 1–32 letters, digits, or underscores.")
    if not 12<=len(password)<=128:
        raise ValueError("Password must be between 12 and 128 characters.")


def _sql_string_literal(value):
    value=str(value)
    if any(ord(ch)<32 or ord(ch)==127 for ch in value):
        raise ValueError("Control characters are not allowed.")
    return "'" + value.replace("'","''") + "'"


def build_postgresql_user_sql(username,password,database):
    """Create a local PostgreSQL login scoped to one existing database."""
    _validate_access_credentials(username,password)
    if not re.fullmatch(r"[A-Za-z0-9_]{1,63}",database or ""):
        raise ValueError("Database name must contain 1–63 letters, digits, or underscores.")
    role='"'+username+'"'
    db='"'+database+'"'
    return (
        f"CREATE ROLE {role} WITH LOGIN PASSWORD {_sql_string_literal(password)};\n"
        f"GRANT CONNECT ON DATABASE {db} TO {role};\n"
        f"GRANT USAGE, CREATE ON SCHEMA public TO {role};\n"
        f"GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO {role};\n"
        f"GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO {role};\n"
    )


def build_redis_acl_command(username,password,key_pattern):
    """Build a RESP command for a non-admin Redis application ACL user."""
    _validate_access_credentials(username,password)
    if (not re.fullmatch(r"[A-Za-z0-9:_*.-]{1,128}",key_pattern or "")
            or key_pattern.startswith("*") or key_pattern=="*"):
        raise ValueError("Key pattern must start with a literal prefix and may contain letters, digits, colon, underscore, dot, hyphen, and *.")
    args=["ACL","SETUSER",username,"reset","on",">"+password,"~"+key_pattern,
          "+@read","+@write","+@connection","+@transaction"]
    chunks=[f"*{len(args)}\r\n"]
    for arg in args:
        chunks.append(f"${len(arg.encode('utf-8'))}\r\n")
        chunks.append(arg+"\r\n")
    return "".join(chunks)



def redis_acl_user_exists(acl_list,username):
    """Return whether ACL LIST contains the exact Redis username."""
    return any(
        line.startswith("user "+username+" ")
        or line=="user "+username
        for line in acl_list.splitlines()
    )


def github_cli_auth_status(profile):
    """Return (label, detail) for the selected GitHub account without exposing credentials."""
    if not shutil.which("gh"):
        return "CLI missing", "GitHub CLI is not installed"
    host=(profile.get("host") or "github.com").strip()
    username=(profile.get("username") or "").strip()
    try:
        result=subprocess.run(
            ["gh","auth","status","--hostname",host],
            capture_output=True,text=True,timeout=10,check=False
        )
    except (OSError,subprocess.TimeoutExpired) as exc:
        return "Unknown", str(exc)
    output=(result.stdout or "")+"\n"+(result.stderr or "")
    # gh reports one or more accounts; identify this profile's exact account.
    account_pattern=rf"Logged in to {re.escape(host)} account {re.escape(username)}(?:\s|$)"
    match=re.search(account_pattern,output,re.IGNORECASE)
    if match:
        tail=output[match.end():].splitlines()
        active=any("Active account: true" in line for line in tail[:3])
        if active:
            return "Authenticated", f"GitHub account: {username} (active)"
        return "Authenticated (inactive)", f"GitHub account: {username} is saved but not active"
    if result.returncode==0:
        return "Not authenticated", f"No saved GitHub CLI login for {username} on {host}"
    return "Not authenticated", f"GitHub CLI has no usable login for {username} on {host}"


def install_desktop_shortcuts():
    """Install a self-contained launcher in a stable per-user location."""
    source_script=Path(__file__).resolve()
    data_home=Path(os.environ.get("XDG_DATA_HOME",HOME/".local/share")).expanduser()
    install_dir=data_home/"devpilot"
    install_dir.mkdir(parents=True,exist_ok=True)
    installed_script=install_dir/"linux_work_setup.py"
    # Copy atomically so launching from the installed copy can also update itself.
    if source_script != installed_script.resolve():
        temp_script=install_dir/".linux_work_setup.py.tmp"
        shutil.copy2(source_script,temp_script)
        os.replace(temp_script,installed_script)
    source_assets=source_script.parent/"assets"
    target_assets=install_dir/"assets"
    if source_assets.is_dir() and source_assets.resolve()!=target_assets.resolve():
        if target_assets.exists():
            shutil.rmtree(target_assets)
        shutil.copytree(source_assets,target_assets)

    icon_source=target_assets/"devpilot.svg"
    icon_dir=data_home/"icons"/"hicolor"/"scalable"/"apps"
    applications_dir=data_home/"applications"
    icon_dir.mkdir(parents=True,exist_ok=True)
    applications_dir.mkdir(parents=True,exist_ok=True)
    icon_target=icon_dir/"devpilot.svg"
    if icon_source.is_file():
        shutil.copy2(icon_source,icon_target)
    icon_value=str(icon_target) if icon_target.is_file() else "applications-development"

    escaped_script=str(installed_script).replace("\\","\\\\").replace('"','\\"')
    desktop_entry=(
        "[Desktop Entry]\n"
        "Version=1.0\n"
        "Type=Application\n"
        "Name=DevPilot\n"
        "Comment=Linux development environment manager\n"
        f'Exec=/usr/bin/python3 "{escaped_script}"\n'
        "TryExec=/usr/bin/python3\n"
        f"Icon={icon_value}\n"
        "Terminal=false\n"
        "Categories=Development;Utility;\n"
        "StartupNotify=true\n"
    )
    launcher=applications_dir/"devpilot.desktop"
    atomic_write(launcher,desktop_entry,0o755)

    desktop_dir=None
    if shutil.which("xdg-user-dir"):
        result=run(["xdg-user-dir","DESKTOP"],5)
        if result.returncode==0 and result.stdout.strip():
            candidate=Path(result.stdout.strip()).expanduser()
            if candidate.is_absolute():
                desktop_dir=candidate
    if desktop_dir is None:
        for candidate in (HOME/"Desktop",HOME/"سطح المكتب"):
            if candidate.exists():
                desktop_dir=candidate
                break
    if desktop_dir is None:
        desktop_dir=HOME/"Desktop"
    desktop_dir.mkdir(parents=True,exist_ok=True)
    desktop_launcher=desktop_dir/"DevPilot.desktop"
    atomic_write(desktop_launcher,desktop_entry,0o755)
    os.chmod(desktop_launcher,0o755)
    if shutil.which("gio"):
        try:
            subprocess.run(["gio","set",str(desktop_launcher),"metadata::trusted","true"],
                           capture_output=True,text=True,timeout=5,check=False)
        except (OSError,subprocess.TimeoutExpired):
            pass
    if shutil.which("update-desktop-database"):
        try:
            subprocess.run(["update-desktop-database",str(applications_dir)],
                           capture_output=True,text=True,timeout=5,check=False)
        except (OSError,subprocess.TimeoutExpired):
            pass
    return launcher,desktop_launcher

class App(tk.Tk):
    def __init__(self):
        super().__init__(); self.title("DevPilot — v"+APP_VERSION)
        self.geometry("1080x740"); self.minsize(900,620)
        try:
            install_desktop_shortcuts()
        except Exception as e:
            # Launcher creation is best-effort; never prevent the main application from opening.
            print(f"DevPilot desktop shortcut could not be created: {e}")
        self.cfg=Config(); self.backup=Backup(); self.pkgmap={}
        self.agent_rows={}; self.agent_busy=False
        self.db_rows={}; self.db_busy=False
        self._ui(); self.refresh_packages(); self.refresh_database_servers(); self.refresh_workspaces(); self.refresh_profiles(); self.refresh_agents()
    def _ui(self):
        style=ttk.Style(self)
        try:style.theme_use("clam")
        except tk.TclError:pass
        h=ttk.Frame(self,padding=14);h.pack(fill="x")
        ttk.Label(h,text="DevPilot",font=("Sans",17,"bold")).pack(anchor="w")
        ttk.Label(h,text="Development Setup • Database servers • Project Workspaces • Git identities • AI agents",foreground="#555").pack(anchor="w")
        ttk.Button(h,text="Create Desktop Shortcut",command=self.create_desktop_shortcut).pack(anchor="e")
        self.tabs=ttk.Notebook(self);self.tabs.pack(fill="both",expand=True,padx=12,pady=(0,12))
        self.dev=ttk.Frame(self.tabs,padding=10);self.db=ttk.Frame(self.tabs,padding=10);self.ws=ttk.Frame(self.tabs,padding=10)
        self.git=ttk.Frame(self.tabs,padding=10);self.agents=ttk.Frame(self.tabs,padding=10)
        self.back=ttk.Frame(self.tabs,padding=10)
        for frame,label in [(self.dev,"Development Setup"),(self.db,"Database Servers"),(self.ws,"Project Workspaces"),(self.git,"Git Accounts & SSH"),(self.agents,"AI Agents"),(self.back,"Backup & Recovery")]:
            self.tabs.add(frame,text=label)
        self._dev_ui();self._db_ui();self._ws_ui();self._git_ui();self._agents_ui();self._backup_ui()
    def create_desktop_shortcut(self):
        try:
            menu_launcher,desktop_launcher=install_desktop_shortcuts()
            messagebox.showinfo(
                "DevPilot shortcut created",
                f"Application menu launcher:\n{menu_launcher}\n\nDesktop shortcut:\n{desktop_launcher}\n\n"
                "If your desktop asks for confirmation, right-click DevPilot.desktop and choose "
                "'Allow Launching' or 'Trust and Launch'."
            )
        except Exception as exc:
            messagebox.showerror("Could not create shortcut",str(exc))

    def _dev_ui(self):
        bar=ttk.Frame(self.dev);bar.pack(fill="x")
        ttk.Label(bar,text="Select package rows or groups. Status is checked against APT.").pack(side="left")
        ttk.Button(bar,text="Refresh",command=self.refresh_packages).pack(side="right")
        self.pkg=ttk.Treeview(self.dev,columns=("status",),show="tree headings",selectmode="extended")
        self.pkg.heading("#0",text="Package / Group");self.pkg.heading("status",text="Status")
        self.pkg.column("#0",width=650);self.pkg.column("status",width=180,anchor="center")
        self.pkg.pack(fill="both",expand=True,pady=8)
        row=ttk.Frame(self.dev);row.pack(fill="x")
        ttk.Button(row,text="Install missing selected",command=lambda:self.install("Not installed")).pack(side="left")
        ttk.Button(row,text="Update selected",command=lambda:self.install("Update available")).pack(side="left",padx=8)
        self.pbar=ttk.Progressbar(self.dev,mode="indeterminate");self.pbar.pack(fill="x",pady=8)
        self.plabel=ttk.Label(self.dev,text="Ready");self.plabel.pack(anchor="w")
        self.log=tk.Text(self.dev,height=6);self.log.pack(fill="x",pady=5)
    def _db_ui(self):
        ttk.Label(self.db,text="Database server installation and service management",font=("Sans",13,"bold")).pack(anchor="w")
        ttk.Label(
            self.db,
            text="Manage APT-installed MySQL, MariaDB, PostgreSQL, and Redis services. Manually launched servers are detected separately and are never stopped or modified here.",
            wraplength=960,foreground="#555"
        ).pack(anchor="w",pady=(3,8))
        top=ttk.Frame(self.db);top.pack(fill="x")
        ttk.Button(top,text="Refresh status",command=self.refresh_database_servers).pack(side="right")
        self.db_tree=ttk.Treeview(
            self.db,columns=("package","unit","status","version","details"),
            show="tree headings",height=8,selectmode="browse"
        )
        for col,title,width in [
            ("#0","Database server",165),("package","APT package",125),
            ("unit","Systemd unit",110),("status","Service state",115),
            ("version","Installed / candidate version",165),("details","Details",245)
        ]:
            self.db_tree.heading(col,text=title)
            self.db_tree.column(col,width=width,anchor="w")
        self.db_tree.pack(fill="both",expand=True,pady=8)
        actions=ttk.Frame(self.db);actions.pack(fill="x")
        self.db_install_btn=ttk.Button(actions,text="Install / Update selected",command=self.install_selected_database_server)
        self.db_install_btn.pack(side="left")
        self.db_start_btn=ttk.Button(actions,text="Start",command=lambda:self.database_service_action("start"))
        self.db_start_btn.pack(side="left",padx=(7,0))
        self.db_stop_btn=ttk.Button(actions,text="Stop",command=lambda:self.database_service_action("stop"))
        self.db_stop_btn.pack(side="left",padx=(7,0))
        self.db_restart_btn=ttk.Button(actions,text="Restart",command=lambda:self.database_service_action("restart"))
        self.db_restart_btn.pack(side="left",padx=(7,0))
        self.db_enable_btn=ttk.Button(actions,text="Enable at boot",command=lambda:self.database_service_action("enable"))
        self.db_enable_btn.pack(side="left",padx=(7,0))
        self.db_disable_btn=ttk.Button(actions,text="Disable at boot",command=lambda:self.database_service_action("disable"))
        self.db_disable_btn.pack(side="left",padx=(7,0))
        access_actions=ttk.Frame(self.db);access_actions.pack(fill="x",pady=(4,0))
        ttk.Label(access_actions,text="Access configuration:").pack(side="left",padx=(0,8))
        self.db_access_buttons={}
        for server_id,label in (
            ("mysql","Configure MySQL Access…"),
            ("mariadb","Configure MariaDB Access…"),
            ("postgresql","Configure PostgreSQL Access…"),
            ("redis","Configure Redis ACL…"),
        ):
            button=ttk.Button(
                access_actions,text=label,
                command=lambda sid=server_id:self.configure_database_access(sid)
            )
            button.pack(side="left",padx=(0,6))
            self.db_access_buttons[server_id]=button
        self.db_service_buttons=[self.db_start_btn,self.db_stop_btn,self.db_restart_btn,self.db_enable_btn,self.db_disable_btn]
        self.db_progress=ttk.Progressbar(self.db,mode="indeterminate")
        self.db_progress.pack(fill="x",pady=(8,3))
        self.db_status_label=ttk.Label(self.db,text="Ready",foreground="#555")
        self.db_status_label.pack(anchor="w")
        self.db_log=tk.Text(self.db,height=5,wrap="word")
        self.db_log.pack(fill="x",pady=(5,0))
        self.db_tree.bind("<<TreeviewSelect>>",self._db_selection_changed)
        self._db_selection_changed()


    def configure_mysql_access(self):
        """Backward-compatible entry point for the MySQL access button."""
        self.configure_database_access("mysql")

    def configure_database_access(self,server_id):
        labels={"mysql":"MySQL","mariadb":"MariaDB","postgresql":"PostgreSQL","redis":"Redis"}
        label=labels.get(server_id)
        if not label:return
        record=self.db_rows.get(server_id)
        if not record or not record.get("managed") or record.get("package_state")=="Not installed":
            messagebox.showinfo(f"{label} is not installed",f"Install the {label} Server first, then configure access.")
            return
        if record.get("active")!="active":
            messagebox.showinfo(f"{label} is not running",f"Start the {label} Server before configuring access.")
            return
        binaries={"mysql":("mysql",),"mariadb":("mariadb","mysql"),"postgresql":("psql",),"redis":("redis-cli",)}
        executable=next((shutil.which(name) for name in binaries[server_id] if shutil.which(name)),None)
        if not shutil.which("pkexec") or not executable:
            messagebox.showerror("Required tools missing",f"DevPilot needs pkexec and a client executable ({', '.join(binaries[server_id])}).")
            return

        dialog=tk.Toplevel(self)
        dialog.title(f"Configure {label} Access")
        dialog.transient(self);dialog.grab_set();dialog.resizable(False,False)
        body=ttk.Frame(dialog,padding=16);body.pack(fill="both",expand=True)
        ttk.Label(body,text=f"Create a local {label} application account",font=("Sans",12,"bold")).grid(
            row=0,column=0,columnspan=2,sticky="w",pady=(0,6)
        )
        descriptions={
            "mysql":"Uses local root socket authentication. Grants access only to the selected database.",
            "mariadb":"Uses local root socket authentication. Grants access only to the selected database.",
            "postgresql":"Uses the local postgres system account. Grants access only to the selected database and public schema.",
            "redis":"Uses local Redis ACL administration. Grants read/write application commands only for the selected key pattern.",
        }
        ttk.Label(body,text=descriptions[server_id],wraplength=490,foreground="#555").grid(
            row=1,column=0,columnspan=2,sticky="w",pady=(0,12)
        )
        ttk.Label(body,text="Username").grid(row=2,column=0,sticky="w",pady=4)
        username=tk.StringVar(value="devpilot_app")
        ttk.Entry(body,textvariable=username,width=34).grid(row=2,column=1,sticky="ew",pady=4)
        ttk.Label(body,text="Password (12–128 characters)").grid(row=3,column=0,sticky="w",pady=4)
        password=tk.StringVar()
        ttk.Entry(body,textvariable=password,show="•",width=34).grid(row=3,column=1,sticky="ew",pady=4)
        ttk.Label(body,text="Confirm password").grid(row=4,column=0,sticky="w",pady=4)
        confirm=tk.StringVar()
        ttk.Entry(body,textvariable=confirm,show="•",width=34).grid(row=4,column=1,sticky="ew",pady=4)
        scope=tk.StringVar(value="app_db" if server_id!="redis" else "app:*")
        if server_id=="redis":
            ttk.Label(body,text="Allowed key pattern").grid(row=5,column=0,sticky="w",pady=4)
            ttk.Entry(body,textvariable=scope,width=34).grid(row=5,column=1,sticky="ew",pady=4)
            scope_note="Redis ACLs are command/key based; they do not isolate logical Redis databases."
        else:
            ttk.Label(body,text="Existing database name").grid(row=5,column=0,sticky="w",pady=4)
            ttk.Entry(body,textvariable=scope,width=34).grid(row=5,column=1,sticky="ew",pady=4)
            scope_note="The database must already exist. DevPilot will not create, drop, or migrate databases."
        ttk.Label(body,text=scope_note,wraplength=490,foreground="#555").grid(
            row=6,column=0,columnspan=2,sticky="w",pady=(8,4)
        )
        body.columnconfigure(1,weight=1)
        buttons=ttk.Frame(body);buttons.grid(row=7,column=0,columnspan=2,sticky="e",pady=(14,0))
        ttk.Button(buttons,text="Cancel",command=dialog.destroy).pack(side="right",padx=(6,0))

        def submit():
            user=username.get().strip()
            secret=password.get()
            if secret!=confirm.get():
                messagebox.showerror("Password mismatch","The passwords do not match.",parent=dialog);return
            try:
                if server_id in ("mysql","mariadb"):
                    payload=build_mysql_user_sql(user,secret,"database",scope.get().strip())
                    access_scope=f"database '{scope.get().strip()}' only"
                elif server_id=="postgresql":
                    payload=build_postgresql_user_sql(user,secret,scope.get().strip())
                    access_scope=f"database '{scope.get().strip()}' and its public schema"
                else:
                    payload=build_redis_acl_command(user,secret,scope.get().strip())
                    access_scope=f"Redis keys matching '{scope.get().strip()}' and application read/write commands"
            except ValueError as exc:
                messagebox.showerror("Invalid account details",str(exc),parent=dialog);return
            if not messagebox.askyesno(
                f"Confirm {label} account",
                f"Create '{user}' with access to {access_scope}?\n\nExisting accounts are never overwritten. DevPilot will not save the password.",
                parent=dialog
            ):return
            dialog.destroy()
            for button in self.db_access_buttons.values():button.configure(state="disabled")
            self.db_status_label.config(text=f"Waiting for administrator authorization ({label})…")
            self.db_progress.start(12)
            def worker():
                try:
                    if server_id in ("mysql","mariadb"):
                        command=["pkexec",executable,"--protocol=socket","-u","root","--batch","--skip-column-names"]
                    elif server_id=="postgresql":
                        command=["pkexec","--user","postgres",executable,"--no-psqlrc","--set","ON_ERROR_STOP=1","--dbname",scope.get().strip()]
                    elif server_id=="redis":
                        check=subprocess.run(
                            ["pkexec",executable,"--raw","ACL","LIST"],
                            capture_output=True,text=True,timeout=30,check=False
                        )
                        if check.returncode:
                            code=check.returncode
                            detail=(check.stderr or check.stdout or "Redis ACL inspection failed.").strip()
                        elif redis_acl_user_exists(check.stdout,user):
                            code=1
                            detail=f"Redis user '{user}' already exists. Existing ACL users are never modified."
                        else:
                            command=["pkexec",executable,"--pipe"]
                            result=subprocess.run(command,input=payload,capture_output=True,text=True,timeout=60,check=False)
                            code=result.returncode
                            detail=(result.stderr or result.stdout or "").strip()
                    else:
                        result=subprocess.run(command,input=payload,capture_output=True,text=True,timeout=60,check=False)
                        code=result.returncode
                        detail=(result.stderr or result.stdout or "").strip()
                except (OSError,subprocess.TimeoutExpired) as exc:
                    code=1;detail=str(exc)
                self.after(0,self._database_access_done,server_id,label,user,code,detail)
            threading.Thread(target=worker,daemon=True).start()
        ttk.Button(buttons,text="Create account",command=submit).pack(side="right")
        dialog.bind("<Escape>",lambda _event:dialog.destroy())
        dialog.wait_window()

    def _database_access_done(self,server_id,label,username,code,detail):
        self.db_progress.stop()
        self._db_selection_changed()
        if code==0:
            self.db_status_label.config(text=f"{label} account '{username}' created successfully.")
            messagebox.showinfo(
                f"{label} access configured",
                f"Account '{username}' was created successfully.\n\n"
                "Use the server's local host and port in your database client.\n"
                "DevPilot did not save the password."
            )
        else:
            self.db_status_label.config(text=f"{label} account creation failed or was cancelled.")
            safe_detail=detail[-1800:] if detail else "Administrator authorization was cancelled or the server returned an error."
            if "already exists" in safe_detail.lower() or "duplicate" in safe_detail.lower():
                safe_detail+="\n\nThe existing account was left unchanged."
            messagebox.showerror(f"Could not configure {label} access",safe_detail)

    def _ws_ui(self):
        r=ttk.Frame(self.ws);r.pack(fill="x")
        ttk.Label(r,text="Workspace root").pack(side="left")
        self.rootvar=tk.StringVar(value=self.cfg.data["settings"]["workspace_root"])
        ttk.Entry(r,textvariable=self.rootvar).pack(side="left",fill="x",expand=True,padx=6)
        ttk.Button(r,text="Browse",command=self.browse_root).pack(side="left")
        ttk.Button(r,text="Save root",command=self.save_root).pack(side="left",padx=5)
        self.wst=ttk.Treeview(self.ws,columns=("path","profile"),show="tree headings")
        self.wst.heading("#0",text="Workspace");self.wst.heading("path",text="Directory");self.wst.heading("profile",text="Git profile")
        self.wst.column("#0",width=180);self.wst.column("path",width=550);self.wst.column("profile",width=180)
        self.wst.pack(fill="both",expand=True,pady=8)
        row=ttk.Frame(self.ws);row.pack(fill="x")
        ttk.Button(row,text="Create workspace",command=self.add_ws).pack(side="left")
        ttk.Button(row,text="Register existing folder",command=self.import_ws).pack(side="left",padx=6)
        ttk.Button(row,text="Assign Git profile…",command=self.assign_profile).pack(side="left")
        ttk.Button(row,text="Refresh",command=self.refresh_workspaces).pack(side="left",padx=6)
        ttk.Button(row,text="Apply assigned profiles",command=self.apply_workspace_profiles).pack(side="left",padx=6)
        ttk.Label(self.ws,text="A profile assigned to a workspace applies to repositories under that directory through Git conditional includes. Repository-local Git settings remain untouched.",wraplength=900,foreground="#555").pack(anchor="w",pady=10)
    def _git_ui(self):
        ttk.Label(self.git,text="Git profiles",font=("Sans",13,"bold")).pack(anchor="w")
        self.gitt=ttk.Treeview(self.git,columns=("name","email","auth","alias","status"),show="headings",height=9)
        for c,t,w in [("name","Profile / Git name",180),("email","Commit email",220),("auth","Method",85),("alias","SSH host alias",170),("status","GitHub status",220)]:
            self.gitt.heading(c,text=t);self.gitt.column(c,width=w)
        self.gitt.pack(fill="both",expand=True,pady=8)
        row=ttk.Frame(self.git);row.pack(fill="x")
        ttk.Button(row,text="Add Git account",command=self.add_profile).pack(side="left")
        ttk.Button(row,text="Edit selected",command=self.edit_profile).pack(side="left",padx=6)
        ttk.Button(row,text="Remove selected",command=self.remove_profile).pack(side="left")
        ttk.Button(row,text="Generate SSH key",command=self.generate_key).pack(side="left",padx=6)
        ttk.Button(row,text="Apply Git / SSH configuration",command=self.apply_git).pack(side="left")
        ttk.Button(row,text="Apply to project folder…",command=self.apply_git_to_folder).pack(side="left",padx=(6,0))
        ttk.Button(row,text="Set up HTTPS authentication",command=self.setup_https_authentication).pack(side="left",padx=(6,0))
        ttk.Button(row,text="Refresh auth status",command=self.refresh_profiles).pack(side="left",padx=(6,0))
        ttk.Label(self.git,text="SSH: each account gets a distinct key and Host alias. HTTPS: select an HTTPS profile and use Set up HTTPS authentication to sign in with GitHub CLI; DevPilot never asks for or stores your password or token.",wraplength=930,foreground="#555").pack(anchor="w",pady=10)
        self.gitstatus=ttk.Label(self.git,text="No changes applied yet.",foreground="#555");self.gitstatus.pack(anchor="w")
    def setup_https_authentication(self):
        selection=self.gitt.selection()
        if not selection:
            messagebox.showinfo("Select Git profile","Select the HTTPS Git profile you want to authenticate.")
            return
        profile=next((p for p in self.cfg.data["git_profiles"] if p["id"]==selection[0]),None)
        if not profile:
            messagebox.showerror("Profile not found","Refresh the Git profiles and try again.")
            return
        if profile.get("auth")!="https":
            messagebox.showinfo("SSH profile selected","This profile uses SSH. HTTPS authentication setup is only for HTTPS profiles.")
            return
        host=profile.get("host","github.com").strip()
        if not host or any(ch in host for ch in "/\\ \t\r\n"):
            messagebox.showerror("Invalid Git host","The profile's Git host is invalid.")
            return
        if not messagebox.askyesno("Set up HTTPS authentication",
            f"Configure secure HTTPS authentication for {host}?\n\n"
            "DevPilot will use GitHub CLI's browser/device login and configure Git to use its credential helper. "
            "Your GitHub password or token will not be entered into or stored by DevPilot."):
            return
        if not shutil.which("gh"):
            if not messagebox.askyesno("GitHub CLI required",
                "GitHub CLI (gh) is not installed. DevPilot will install it using APT. "
                "A progress window will remain visible while the system authorization prompt is handled."):
                return
            self._install_gh_async(profile)
            return
        self._launch_gh_login(profile)

    def _install_gh_async(self, profile):
        progress=tk.Toplevel(self)
        progress.title("Installing GitHub CLI")
        progress.transient(self)
        progress.resizable(False,False)
        ttk.Label(progress,text="Installing GitHub CLI (gh)…",font=("Sans",11,"bold")).pack(padx=18,pady=(16,6))
        ttk.Label(progress,text="Please approve the system authentication prompt if it appears.\nThis may take a few minutes.",justify="center").pack(padx=18,pady=4)
        bar=ttk.Progressbar(progress,mode="indeterminate",length=340)
        bar.pack(padx=18,pady=12)
        bar.start(12)
        status=tk.StringVar(value="Waiting for APT / administrator approval…")
        ttk.Label(progress,textvariable=status).pack(padx=18,pady=(0,14))
        progress.protocol("WM_DELETE_WINDOW",lambda:status.set("Installation continues in the background…"))
        def worker():
            try:
                result=subprocess.run(["pkexec","apt-get","install","-y","gh"],capture_output=True,text=True,check=False)
                code=result.returncode
                output=(result.stdout or "")+"\n"+(result.stderr or "")
            except OSError as exc:
                code=127;output=str(exc)
            self.after(0,lambda:self._finish_gh_install(progress,bar,status,profile,code,output))
        threading.Thread(target=worker,daemon=True).start()

    def _finish_gh_install(self, progress, bar, status, profile, code, output):
        try:
            bar.stop()
            progress.destroy()
        except tk.TclError:
            pass
        if code==0 and shutil.which("gh"):
            self.gitstatus.config(text="GitHub CLI installed successfully. Starting secure browser sign-in…")
            self._launch_gh_login(profile)
        else:
            detail=output.strip()[-2500:] or "APT installation failed or was cancelled."
            messagebox.showerror("GitHub CLI installation failed",detail)
            self.gitstatus.config(text="GitHub CLI installation failed. See the error details.")

    def _launch_gh_login(self, profile):
        host=profile.get("host","github.com").strip()
        if not profile.get("username","").strip():
            messagebox.showerror("Missing GitHub username","Edit this Git profile and enter its GitHub username first.")
            return
        quoted_host=shlex.quote(host)
        expected_login=shlex.quote(profile.get("username","").strip())
        if not profile.get("username","").strip():
            messagebox.showerror("Missing GitHub username","Edit this Git profile and enter its GitHub username first.")
            return
        command=(f"gh auth login --hostname {quoted_host} --git-protocol https --web && "
                 f"login=$(gh api user --hostname {quoted_host} --jq .login) && "
                 f"if [ \"$login\" != {expected_login} ]; then "
                 f"echo 'Signed-in GitHub account does not match this DevPilot profile.'; "
                 "echo \"Authenticated: $login\"; "
                 "exit 1; fi && "
                 f"gh auth setup-git --hostname {quoted_host}; rc=$?; "
                 "printf '\n\nHTTPS authentication setup finished (exit code %s).\n' \"$rc\"; "
                 "read -r -n 1 -s -p 'Press any key to close this terminal…'")
        terminal_specs=[
            ("x-terminal-emulator",lambda term:[term,"-e","bash","-lc",command]),
            ("gnome-terminal",lambda term:[term,"--","bash","-lc",command]),
            ("xfce4-terminal",lambda term:[term,"--command",f"bash -lc {shlex.quote(command)}"]),
            ("konsole",lambda term:[term,"-e","bash","-lc",command]),
            ("kitty",lambda term:[term,"bash","-lc",command]),
            ("alacritty",lambda term:[term,"-e","bash","-lc",command]),
        ]
        for name,builder in terminal_specs:
            terminal=shutil.which(name)
            if not terminal:continue
            try:
                process=subprocess.Popen(builder(terminal),cwd=str(HOME),start_new_session=True)
                self.gitstatus.config(text=f"GitHub CLI HTTPS sign-in started for {host}. Complete browser authorization; status will refresh when the terminal closes.")
                def refresh_after_login():
                    process.wait()
                    try:
                        self.after(0,self.refresh_profiles)
                    except tk.TclError:
                        pass
                threading.Thread(target=refresh_after_login,daemon=True).start()
                return
            except OSError as exc:
                self.gitstatus.config(text=f"Could not launch {name}: {exc}")
        messagebox.showerror("Terminal not found","No supported terminal emulator was found. Install a terminal emulator and try again.")

    def _backup_ui(self):
        ttk.Label(self.back,text="Creates timestamped copies before applying managed Git/SSH changes. Private SSH keys are excluded.",wraplength=900).pack(anchor="w")
        ttk.Button(self.back,text="Create backup now",command=self.do_backup).pack(anchor="w",pady=10)
        self.backlog=tk.Text(self.back,height=18);self.backlog.pack(fill="both",expand=True)
    def _agents_ui(self):
        ttk.Label(self.agents,text="AI coding agents for your terminal",font=("Sans",13,"bold")).pack(anchor="w")
        ttk.Label(self.agents,text="Install, update, check, and launch official terminal agents. Installers run as your user; no sudo is used.",wraplength=960,foreground="#555").pack(anchor="w",pady=(3,8))
        self.agent_tree=ttk.Treeview(self.agents,columns=("status","version","command"),show="tree headings",height=7,selectmode="browse")
        ttk.Button(self.agents,text="Refresh status",command=self.refresh_agents).pack(anchor="e")
        for col,title,width in [("#0","Agent",220),("status","Status",150),("version","Version",220),("command","Terminal command",180)]:
            self.agent_tree.heading(col,text=title);self.agent_tree.column(col,width=width)
        self.agent_tree.pack(fill="both",expand=True,pady=8)
        details=ttk.LabelFrame(self.agents,text="Launch directory",padding=8);details.pack(fill="x",pady=(0,8))
        default_dir=Path(self.cfg.data["settings"].get("workspace_root",str(HOME/"Projects"))).expanduser()
        if not default_dir.is_dir():default_dir=HOME
        self.agent_workdir=tk.StringVar(value=str(default_dir))
        ttk.Entry(details,textvariable=self.agent_workdir).pack(side="left",fill="x",expand=True)
        ttk.Button(details,text="Browse…",command=self.browse_agent_workdir).pack(side="left",padx=(6,0))
        ttk.Button(details,text="Use selected workspace",command=self.use_selected_workspace).pack(side="left",padx=(6,0))
        actions=ttk.Frame(self.agents);actions.pack(fill="x")
        self.agent_install_btn=ttk.Button(actions,text="Install / Update selected",command=self.install_selected_agent);self.agent_install_btn.pack(side="left")
        self.agent_launch_btn=ttk.Button(actions,text="Launch in Terminal",command=self.launch_selected_agent);self.agent_launch_btn.pack(side="left",padx=8)
        self.agent_progress=ttk.Progressbar(self.agents,mode="indeterminate");self.agent_progress.pack(fill="x",pady=(8,3))
        self.agent_status_label=ttk.Label(self.agents,text="Ready",foreground="#555");self.agent_status_label.pack(anchor="w")
        self.agent_log=tk.Text(self.agents,height=7,wrap="word");self.agent_log.pack(fill="x",pady=(5,0))
        self.agent_tree.bind("<<TreeviewSelect>>",self._agent_selection_changed)
    def refresh_packages(self):
        self.pkg.delete(*self.pkg.get_children());self.pkgmap={}
        for group,pkgs in GROUPS.items():
            gid="g"+str(len(self.pkgmap));self.pkg.insert("","end",iid=gid,text=group,values=("",),open=True)
            for pkg in pkgs:
                state=installed_state(pkg);iid="p"+str(len(self.pkgmap));self.pkgmap[iid]=(pkg,state)
                self.pkg.insert(gid,"end",iid=iid,text=pkg,values=(state,))
        self.plabel.config(text="Package status refreshed.")
    def install(self,state):
        selected=[]
        for iid in self.pkg.selection():
            if iid in self.pkgmap:
                p,s=self.pkgmap[iid]
                if s==state:selected.append(p)
            else:
                for ch in self.pkg.get_children(iid):
                    if ch in self.pkgmap and self.pkgmap[ch][1]==state:selected.append(self.pkgmap[ch][0])
        selected=list(dict.fromkeys(selected))
        if not selected:messagebox.showinfo("No packages","No selected packages match this action.");return
        if not messagebox.askyesno("Confirm","Run APT for:\n"+", ".join(selected)):return
        self.pbar.start(12);self.plabel.config(text="APT is running…")
        threading.Thread(target=self._apt,args=(selected,),daemon=True).start()
    def _apt(self,pkgs):
        try:
            p=subprocess.Popen(["pkexec","apt-get","install","-y"]+pkgs,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
            for line in p.stdout:self.after(0,lambda x=line:self.log.insert("end",x))
            code=p.wait();self.after(0,self._apt_done,code)
        except Exception as e:self.after(0,self._apt_done,1,str(e))
    def _apt_done(self,code,err=None):
        self.pbar.stop();self.plabel.config(text="APT completed." if code==0 else f"APT failed ({code})")
        if err:self.log.insert("end",str(err))
        self.refresh_packages()
        self.refresh_database_servers()

    def refresh_database_servers(self):
        if not hasattr(self,"db_tree"):return
        self.db_tree.delete(*self.db_tree.get_children())
        self.db_rows={}
        managed_active_ports=set()
        for server in DATABASE_SERVERS:
            package_state=installed_state(server["package"])
            service=database_service_state(server["service"]) if package_state!="Not installed" else {
                "unit_available":False,"active":"not installed","enabled":"—"
            }
            if service["unit_available"] and service["active"]=="active":
                managed_active_ports.add(server["port"])
            version=database_package_version(server["package"])
            details=f"APT: {package_state} · Auto-start: {service['enabled']}"
            self.db_rows[server["id"]]={
                "managed":True,"server":server,"package_state":package_state,
                "unit_available":service["unit_available"],"active":service["active"],
                "enabled":service["enabled"],
            }
            self.db_tree.insert(
                "","end",iid=server["id"],text=server["name"],
                values=(server["package"],server["service"],service["active"],version,details)
            )
        ps=run(["ps","-eo","pid=,args="],8)
        if ps.returncode==0:
            for process in parse_unmanaged_database_processes(ps.stdout):
                if process["port"] in managed_active_ports:continue
                details=[f"PID {process['pid']}",f"Port {process['port']}"]
                if process["datadir"]:details.append(f"Data: {process['datadir']}")
                if process["socket"]:details.append(f"Socket: {process['socket']}")
                iid="external-"+process["pid"]
                self.db_rows[iid]={"managed":False,"process":process}
                self.db_tree.insert(
                    "","end",iid=iid,text=process["name"]+" (unmanaged)",
                    values=("External binary","No systemd unit","Running (manual)","—"," · ".join(details))
                )
        self.db_status_label.config(text="Database server status refreshed. Unmanaged processes are read-only here.")
        self._db_selection_changed()

    def _db_selection_changed(self,event=None):
        if not hasattr(self,"db_install_btn"):return
        selected=self.db_tree.selection()
        record=self.db_rows.get(selected[0]) if selected else None
        available=bool(record and record.get("managed") and not self.db_busy)
        can_manage=bool(
            available and record.get("package_state")!="Not installed"
            and record.get("unit_available")
        )
        self.db_install_btn.config(state="normal" if available else "disabled")
        for button in self.db_service_buttons:
            button.config(state="normal" if can_manage else "disabled")
        selected_id=selected[0] if selected else None
        for server_id,button in self.db_access_buttons.items():
            enabled=bool(
                selected_id==server_id and record and record.get("managed")
                and record.get("package_state")!="Not installed"
                and record.get("active")=="active" and not self.db_busy
            )
            button.config(state="normal" if enabled else "disabled")

    def _selected_database_server(self):
        selected=self.db_tree.selection()
        if not selected:
            messagebox.showinfo("Select a database server","Select a database server first.")
            return None
        record=self.db_rows.get(selected[0])
        if not record or not record.get("managed"):
            messagebox.showinfo(
                "Unmanaged database process",
                "This server was started outside APT/systemd. DevPilot will not stop, restart, or modify it. Manage it from the tool or script that launched it."
            )
            return None
        return record

    def _database_log(self,message):
        self.db_log.insert("end",message)
        self.db_log.see("end")

    def _start_database_task(self,command,label):
        if self.db_busy:return
        if not shutil.which("pkexec"):
            messagebox.showerror("Missing dependency","pkexec is required for privileged database server operations.")
            return
        self.db_busy=True
        self._db_selection_changed()
        self.db_progress.start(12)
        self.db_status_label.config(text=label+"…")
        self._database_log(f"\n$ {' '.join(shlex.quote(part) for part in command)}\n")
        threading.Thread(
            target=self._database_task_worker,args=(command,label),daemon=True
        ).start()

    def _database_task_worker(self,command,label):
        code=1;error=None
        try:
            process=subprocess.Popen(
                command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                text=True,bufsize=1
            )
            if process.stdout:
                for line in process.stdout:self.after(0,self._database_log,line)
            code=process.wait()
        except Exception as exc:error=str(exc)
        self.after(0,self._database_task_done,label,code,error)

    def _database_task_done(self,label,code,error=None):
        self.db_progress.stop()
        self.db_busy=False
        if error:self._database_log(f"\nError: {error}\n")
        self._database_log(f"\n{label} finished with exit code {code}.\n")
        self.refresh_packages()
        self.refresh_database_servers()
        self.db_status_label.config(
            text=f"{label} completed." if code==0 else f"{label} failed (exit code {code}). Check the log."
        )
        self._db_selection_changed()

    def _external_processes_on_port(self,port):
        return [
            row["process"] for row in self.db_rows.values()
            if not row.get("managed") and row.get("process",{}).get("port")==port
        ]

    def install_selected_database_server(self):
        record=self._selected_database_server()
        if not record or self.db_busy:return
        server=record["server"]
        for conflict_id in server.get("conflicts",[]):
            conflict=self.db_rows.get(conflict_id)
            if conflict and conflict.get("package_state")!="Not installed":
                messagebox.showerror(
                    "Conflicting database servers",
                    f"{server['name']} and {conflict['server']['name']} cannot be installed together using their default APT configuration. Remove the other server only after backing up its databases."
                )
                return
        external=self._external_processes_on_port(server["port"])
        if external:
            process=external[0]
            messagebox.showwarning(
                "Database port already in use",
                f"An unmanaged database process is already using port {server['port']} (PID {process['pid']}).\n\n"
                f"Data directory: {process['datadir'] or 'not reported'}\n\n"
                "DevPilot will not install another server on that port. Inspect and safely stop or migrate the existing instance first."
            )
            return
        action="Install" if record["package_state"]=="Not installed" else "Update"
        if action=="Install":
            command=["pkexec","apt-get","install","-y",server["package"]]
        else:
            command=["pkexec","apt-get","install","--only-upgrade","-y",server["package"]]
        prompt=(
            f"{action} {server['name']} using APT package {server['package']}?\n\n"
            f"APT will use the candidate version from your configured repositories.\n"
            "The package may create a system data directory and start/enable its systemd service. "
            "DevPilot will not import or overwrite an unmanaged data directory.\n\nContinue?"
        )
        if not messagebox.askyesno(f"Confirm database server {action.lower()}",prompt):return
        self._start_database_task(command,f"{action} {server['name']}")

    def database_service_action(self,action):
        record=self._selected_database_server()
        if not record or self.db_busy:return
        if record["package_state"]=="Not installed" or not record["unit_available"]:
            messagebox.showinfo("Service unavailable","Install the APT server package and ensure its systemd unit exists first.")
            return
        server=record["server"]
        if action in ("start","restart"):
            external=self._external_processes_on_port(server["port"])
            if external:
                process=external[0]
                messagebox.showwarning(
                    "Database port already in use",
                    f"An unmanaged process is using port {server['port']} (PID {process['pid']}). Stop or reconfigure it before starting this systemd service."
                )
                return
        titles={"start":"Start","stop":"Stop","restart":"Restart","enable":"Enable at boot","disable":"Disable at boot"}
        if action not in titles:return
        command=["pkexec","systemctl",action,server["service"]]
        if not messagebox.askyesno(
            "Confirm database service action",
            f"{titles[action]} {server['name']}?\n\nCommand: systemctl {action} {server['service']}\n\n"
            "This action applies only to the APT/systemd-managed service, not manually launched processes."
        ):return
        self._start_database_task(command,f"{titles[action]} {server['name']}")

    def _agent_env(self):
        env=os.environ.copy()
        extra=[str(HOME/".local"/"bin"),str(HOME/".opencode"/"bin"),str(HOME/".claude"/"bin")]
        env["PATH"]=os.pathsep.join(extra+[env.get("PATH","")])
        return env
    def refresh_agents(self):
        if not hasattr(self,"agent_tree"):return
        self.agent_tree.delete(*self.agent_tree.get_children());self.agent_rows={}
        env=self._agent_env()
        for agent in AI_AGENTS:
            executable=shutil.which(agent["command"],path=env["PATH"])
            status="Not installed";version="—"
            if executable:
                status="Installed";version="Version unavailable"
                try:
                    result=subprocess.run([executable,"--version"],capture_output=True,text=True,timeout=8,check=False,env=env)
                    output=(result.stdout or result.stderr).strip().splitlines()
                    if result.returncode==0 and output:version=output[0][:100]
                except (OSError,subprocess.TimeoutExpired):pass
            self.agent_rows[agent["id"]]={"agent":agent,"executable":executable,"status":status,"version":version}
            self.agent_tree.insert("","end",iid=agent["id"],text=agent["name"],values=(status,version,agent["command"]))
        self.agent_status_label.config(text="Agent status refreshed. Select an agent to install, update, or launch.")
        self._agent_selection_changed()
    def _selected_agent(self):
        selected=self.agent_tree.selection()
        if not selected:
            messagebox.showinfo("Select an agent","Select an AI agent first.");return None
        return self.agent_rows.get(selected[0])
    def _agent_selection_changed(self,event=None):
        if not hasattr(self,"agent_launch_btn"):return
        selected=self.agent_tree.selection();record=self.agent_rows.get(selected[0]) if selected else None
        can_launch=bool(record and record.get("executable") and not self.agent_busy)
        self.agent_launch_btn.config(state="normal" if can_launch else "disabled")
        self.agent_install_btn.config(state="disabled" if self.agent_busy else "normal")
    def browse_agent_workdir(self):
        current=self.agent_workdir.get().strip() or str(HOME)
        path=filedialog.askdirectory(title="Choose a project directory",initialdir=current)
        if path:self.agent_workdir.set(path)
    def use_selected_workspace(self):
        selected=self.wst.selection()
        if not selected:
            messagebox.showinfo("Select workspace","Open Project Workspaces and select a workspace first.");return
        workspace=next((w for w in self.cfg.data["workspaces"] if w["id"]==selected[0]),None)
        if workspace:self.agent_workdir.set(workspace["path"])
    def install_selected_agent(self):
        record=self._selected_agent()
        if not record:return
        if not shutil.which("curl"):
            messagebox.showerror("Missing dependency","curl is required. Install it from the Development Setup tab, then refresh.");return
        agent=record["agent"];action="Install" if not record["executable"] else "Update / reinstall"
        prompt=(f"{action} {agent['name']} using its official installer?\n\n"
                f"Installer source: {agent['docs']}\n\nCommand:\n{agent['install_command']}\n\n"
                "The installer runs as your current Linux user (no sudo) and executes the vendor's installer script. Continue?")
        if not messagebox.askyesno("Confirm AI agent installation",prompt):return
        self.agent_busy=True;self._agent_selection_changed()
        self.agent_progress.start(12);self.agent_status_label.config(text=f"Installing / updating {agent['name']}…")
        self._append_agent_log(f"\n=== {action}: {agent['name']} ===\nSource: {agent['docs']}\n$ {agent['install_command']}\n")
        threading.Thread(target=self._agent_install_worker,args=(agent,),daemon=True).start()
    def _append_agent_log(self,text):
        self.agent_log.insert("end",text);self.agent_log.see("end")
    def _agent_install_worker(self,agent):
        code=1;error=None
        try:
            process=subprocess.Popen(["bash","-lc",agent["install_command"]],cwd=str(HOME),env=self._agent_env(),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
            if process.stdout:
                for line in process.stdout:self.after(0,self._append_agent_log,line)
            code=process.wait()
        except Exception as exc:error=str(exc)
        self.after(0,self._agent_install_done,agent["id"],code,error)
    def _agent_install_done(self,agent_id,code,error=None):
        self.agent_progress.stop();self.agent_busy=False
        if error:self._append_agent_log(f"\nInstaller error: {error}\n")
        self._append_agent_log(f"\nInstaller finished with exit code {code}.\n")
        self.refresh_agents()
        if code==0 and not self.agent_rows.get(agent_id,{}).get("executable"):
            self.agent_status_label.config(text="Installer finished, but command is not on DevPilot's PATH. Restart DevPilot or reopen your session, then Refresh.")
        elif code!=0:self.agent_status_label.config(text=f"Installer failed (exit code {code}). Check the log above.")
        self._agent_selection_changed()
    def launch_selected_agent(self):
        record=self._selected_agent()
        if not record:return
        executable=record.get("executable")
        if not executable:
            messagebox.showinfo("Agent not installed","Install this agent first, then refresh.");return
        directory=Path(self.agent_workdir.get().strip()).expanduser()
        if not directory.is_dir():
            messagebox.showerror("Invalid project directory","Choose an existing project directory before launching the agent.");return
        agent=record["agent"]
        command=(f"cd -- {shlex.quote(str(directory.resolve()))} && {shlex.quote(executable)}; rc=$?; "
                 "printf '\n\nAgent exited with code %s.\n' \"$rc\"; "
                 "read -r -n 1 -s -p 'Press any key to close this terminal…'")
        terminal_specs=[
            ("x-terminal-emulator",lambda term:[term,"-e","bash","-lc",command]),
            ("gnome-terminal",lambda term:[term,"--","bash","-lc",command]),
            ("xfce4-terminal",lambda term:[term,"--command",f"bash -lc {shlex.quote(command)}"]),
            ("konsole",lambda term:[term,"-e","bash","-lc",command]),
            ("kitty",lambda term:[term,"bash","-lc",command]),
            ("alacritty",lambda term:[term,"-e","bash","-lc",command]),
        ]
        env=self._agent_env()
        for name,builder in terminal_specs:
            terminal=shutil.which(name,path=env["PATH"])
            if not terminal:continue
            try:
                subprocess.Popen(builder(terminal),cwd=str(directory),env=env,start_new_session=True)
                self.agent_status_label.config(text=f"Launched {agent['name']} in {directory}");return
            except OSError as exc:self._append_agent_log(f"Could not launch {name}: {exc}\n")
        messagebox.showerror("Terminal not found","No supported terminal emulator was found. Install x-terminal-emulator or GNOME Terminal, then try again.")
    def browse_root(self):
        p=filedialog.askdirectory(initialdir=self.rootvar.get())
        if p:self.rootvar.set(p)
    def save_root(self):
        p=Path(self.rootvar.get()).expanduser()
        if not p.is_absolute():messagebox.showerror("Invalid path","Use an absolute path.");return
        self.cfg.data["settings"]["workspace_root"]=str(p);self.cfg.save()
        messagebox.showinfo("Saved","Workspace root saved.")
    def ask(self,title,fields):
        win=tk.Toplevel(self);win.title(title);win.transient(self);win.grab_set()
        vars={}
        for i,(key,label,default) in enumerate(fields):
            ttk.Label(win,text=label).grid(row=i,column=0,sticky="w",padx=10,pady=6)
            v=tk.StringVar(value=default);vars[key]=v
            ttk.Entry(win,textvariable=v,width=42).grid(row=i,column=1,padx=10,pady=6)
        out={"v":None}
        def ok():out["v"]={k:v.get().strip() for k,v in vars.items()};win.destroy()
        ttk.Button(win,text="Save",command=ok).grid(row=len(fields),column=1,sticky="e",padx=10,pady=10)
        win.wait_window();return out["v"]
    def add_ws(self):
        d=self.ask("Create workspace",[("name","Workspace name","")])
        if not d or not d["name"]:return
        path=Path(self.rootvar.get()).expanduser()/d["name"]
        if path.exists():messagebox.showerror("Exists","Folder already exists. Register it instead.");return
        try:path.mkdir(parents=True)
        except Exception as e:messagebox.showerror("Error",str(e));return
        self._save_ws(d["name"],path)
    def import_ws(self):
        p=filedialog.askdirectory(title="Choose existing workspace")
        if not p:return
        path=Path(p).resolve();d=self.ask("Register folder",[("name","Workspace name",path.name)])
        if d and d["name"]:self._save_ws(d["name"],path)
    def _save_ws(self,name,path):
        self.cfg.data["workspaces"].append({"id":str(uuid.uuid4()),"name":name,"path":str(path),"git_profile_id":None})
        self.cfg.save();self.refresh_workspaces()
    def refresh_workspaces(self):
        if not hasattr(self,"wst"):return
        self.wst.delete(*self.wst.get_children())
        for w in self.cfg.data["workspaces"]:
            pr=next((p["name"] for p in self.cfg.data["git_profiles"] if p["id"]==w.get("git_profile_id")),"Not assigned")
            self.wst.insert("","end",iid=w["id"],text=w["name"],values=(w["path"],pr))
    def refresh_profiles(self):
        if not hasattr(self,"gitt"):return
        self.gitt.delete(*self.gitt.get_children())
        for p in self.cfg.data["git_profiles"]:
            if p.get("auth")=="https":
                status,detail=github_cli_auth_status(p)
            else:
                key=Path(p.get("key_path","")).expanduser()
                status="SSH key ready" if key.is_file() else "SSH key missing"
                detail=str(key)
            self.gitt.insert("","end",iid=p["id"],values=(p["name"],p["email"],p["auth"],p.get("host_alias",""),status))
    def add_profile(self):
        d=self.ask("Add Git account",[("name","Profile label (e.g. TechWills)",""),("git_name","Commit author name",""),("email","Commit email",""),("host","Git host (github.com / gitlab.com)","github.com"),("username","Hosting username",""),("auth","Authentication: ssh or https","ssh")])
        if not d:return
        if not all(d[k] for k in ("name","git_name","email","host","username")):messagebox.showerror("Missing data","Complete all fields.");return
        d["auth"]=d["auth"].lower()
        if d["auth"] not in ("ssh","https"):messagebox.showerror("Invalid auth","Use ssh or https.");return
        pid=str(uuid.uuid4());alias=f"{d['host'].split('.')[0]}-{''.join(c for c in d['name'].lower() if c.isalnum() or c=='-')}"
        self.cfg.data["git_profiles"].append({"id":pid,"name":d["name"],"git_name":d["git_name"],"email":d["email"],"host":d["host"],"username":d["username"],"auth":d["auth"],"host_alias":alias if d["auth"]=="ssh" else "" ,"key_path":str(HOME/".ssh"/f"id_ed25519_{alias}") if d["auth"]=="ssh" else ""})
        self.cfg.save();self.refresh_profiles()
    def selected_profile(self):
        sel=self.gitt.selection()
        if not sel:messagebox.showinfo("Select profile","Select a Git account first.");return None
        return next((p for p in self.cfg.data["git_profiles"] if p["id"]==sel[0]),None)
    def edit_profile(self):
        p=self.selected_profile()
        if not p:return
        d=self.ask("Edit Git account",[("name","Profile label",p["name"]),("git_name","Commit author name",p["git_name"]),("email","Commit email",p["email"]),("host","Git host",p["host"]),("username","Hosting username",p["username"]),("auth","Authentication (ssh or https)",p["auth"])])
        if not d:return
        if not all(d[k] for k in d):messagebox.showerror("Missing data","Complete all fields.");return
        p.update(name=d["name"],git_name=d["git_name"],email=d["email"],host=d["host"],username=d["username"],auth=d["auth"].lower())
        if p["auth"]=="ssh":
            alias=f"{p['host'].split('.')[0]}-{''.join(c for c in p['name'].lower() if c.isalnum() or c=='-')}"
            p["host_alias"]=alias;p["key_path"]=str(HOME/".ssh"/f"id_ed25519_{alias}")
        else:p["host_alias"]="";p["key_path"]=""
        self.cfg.save();self.refresh_profiles();self.refresh_workspaces()
    def remove_profile(self):
        p=self.selected_profile()
        if not p:return
        if not messagebox.askyesno("Remove profile",f"Remove {p['name']}? Workspace assignments will be cleared. Existing keys/config lines are not deleted automatically."):return
        for w in self.cfg.data["workspaces"]:
            if w.get("git_profile_id")==p["id"]:w["git_profile_id"]=None
        self.cfg.data["git_profiles"]=[x for x in self.cfg.data["git_profiles"] if x["id"]!=p["id"]]
        self.cfg.save();self.refresh_profiles();self.refresh_workspaces()
    def generate_key(self):
        p=self.selected_profile()
        if not p:return
        if p["auth"]!="ssh":messagebox.showinfo("HTTPS profile","Switch this profile to SSH to generate a key.");return
        key=Path(p["key_path"]).expanduser()
        if key.exists():
            messagebox.showinfo("Key exists",f"Key already exists:\n{key}\nNo file was overwritten.");return
        key.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        cmd=["ssh-keygen","-t","ed25519","-C",p["email"],"-f",str(key)]
        proc=subprocess.run(cmd,input="\n\n",capture_output=True,text=True)
        if proc.returncode:
            messagebox.showerror("ssh-keygen failed",proc.stderr or proc.stdout);return
        os.chmod(key,0o600);os.chmod(Path(str(key)+".pub"),0o644)
        messagebox.showinfo("SSH key generated",f"Public key:\n{key}.pub\n\nAdd this public key to {p['host']} account. Private key stays on this device.")
        self.refresh_profiles()
    def assign_profile(self):
        sel=self.wst.selection()
        if not sel:messagebox.showinfo("Select workspace","Select a workspace first.");return
        profiles=self.cfg.data["git_profiles"]
        if not profiles:messagebox.showinfo("No profiles","Create a Git account first.");return
        win=tk.Toplevel(self);win.title("Assign Git profile");win.transient(self);win.grab_set()
        w=next(x for x in self.cfg.data["workspaces"] if x["id"]==sel[0])
        opts=["(No profile)"]+[p["name"] for p in profiles]
        var=tk.StringVar(value=next((p["name"] for p in profiles if p["id"]==w.get("git_profile_id")),"(No profile)"))
        ttk.Label(win,text=f"Profile for {w['path']}").pack(padx=12,pady=8)
        ttk.Combobox(win,textvariable=var,values=opts,state="readonly",width=38).pack(padx=12,pady=8)
        def save():
            name=var.get();w["git_profile_id"]=next((p["id"] for p in profiles if p["name"]==name),None)
            self.cfg.save();win.destroy();self.refresh_workspaces()
        ttk.Button(win,text="Save assignment",command=save).pack(pady=10);win.wait_window()
    def do_backup(self):
        try:p=self.backup.create();self.backlog.insert("end",f"Backup created: {p}\n");messagebox.showinfo("Backup complete",str(p))
        except Exception as e:messagebox.showerror("Backup failed",str(e))
    def _git_repository_root(self, folder):
        """Return the Git work-tree root for a folder, or None when it is not a repository."""
        folder=Path(folder).expanduser().resolve()
        result=run(["git","-C",str(folder),"rev-parse","--show-toplevel"],8)
        if result.returncode!=0 or not result.stdout.strip():
            return None
        return Path(result.stdout.strip()).resolve()

    def apply_git_to_folder(self):
        folder=filedialog.askdirectory(title="Choose project folder to configure Git identity")
        if not folder:return
        root=self._git_repository_root(folder)
        if root is None:
            messagebox.showerror("Not a Git repository",f"No Git repository was found in:\n{folder}\n\nSelect an existing Git repository first.")
            return
        profiles=self.cfg.data["git_profiles"]
        if not profiles:
            messagebox.showinfo("No Git profiles","Add a Git account profile first.")
            return
        self._apply_profile_to_repository(root,profiles)

    def apply_git(self):
        # Apply directly to the repository from which DevPilot was launched, if any.
        try:
            cwd=Path.cwd().resolve()
        except OSError:
            cwd=HOME
        repo=self._git_repository_root(cwd)
        profiles=self.cfg.data["git_profiles"]
        if not profiles:
            messagebox.showinfo("No Git profiles","Add a Git account profile first.")
            return
        if repo is not None:
            self._apply_profile_to_repository(repo,profiles)
            return
        # GUI launches often start outside the user's project; let them select it.
        self.apply_git_to_folder()

    def apply_workspace_profiles(self):
        profiles=self.cfg.data["git_profiles"]
        assigned=[w for w in self.cfg.data["workspaces"] if w.get("git_profile_id")]
        if not profiles or not assigned:
            messagebox.showinfo("Nothing to apply","Add Git profiles, assign them to workspaces, and try again.")
            return
        self._apply_workspace_git_configuration(profiles,assigned)

    def _apply_profile_to_repository(self, repo, profiles):
        names=[p["name"] for p in profiles]
        win=tk.Toplevel(self);win.title("Choose Git identity");win.transient(self);win.grab_set()
        selected=tk.StringVar(value=names[0])
        ttk.Label(win,text=f"Apply Git commit identity to repository:\n{repo}",wraplength=560).pack(padx=14,pady=(14,8))
        ttk.Label(win,text="Git profile").pack(anchor="w",padx=14)
        ttk.Combobox(win,textvariable=selected,values=names,state="readonly",width=42).pack(padx=14,pady=6)
        ttk.Label(win,text="Only this repository's local user.name and user.email will change.",wraplength=560,foreground="#555").pack(padx=14,pady=8)
        outcome={"profile":None}
        def apply():
            profile=next((p for p in profiles if p["name"]==selected.get()),None)
            if profile:
                outcome["profile"]=profile
                win.destroy()
        ttk.Button(win,text="Apply identity",command=apply).pack(pady=(2,14))
        win.wait_window()
        profile=outcome["profile"]
        if not profile:return
        if not messagebox.askyesno("Confirm Git identity",f"Set this repository's commit identity?\n\nRepository: {repo}\nName: {profile['git_name']}\nEmail: {profile['email']}"):
            return
        try:
            config_result=run(["git","-C",str(repo),"rev-parse","--git-path","config"],8)
            if config_result.returncode or not config_result.stdout.strip():
                raise RuntimeError(config_result.stderr.strip() or "Could not locate this repository's local Git config.")
            config_path=Path(config_result.stdout.strip())
            if not config_path.is_absolute():
                config_path=(repo/config_path).resolve()
            if not config_path.is_file():
                raise RuntimeError(f"Repository Git config was not found: {config_path}")
            backup=self.backup.create(extra_files=[config_path])
            rollback_copy=backup/"extra"/f"0-{config_path.name}"
            for key,value in (("user.name",profile["git_name"]),("user.email",profile["email"])):
                result=run(["git","-C",str(repo),"config","--local",key,value],8)
                if result.returncode:
                    raise RuntimeError(result.stderr.strip() or f"Could not set {key}")
            actual={}
            for key in ("user.name","user.email"):
                result=run(["git","-C",str(repo),"config","--local","--get",key],8)
                if result.returncode:
                    raise RuntimeError(result.stderr.strip() or f"Could not verify {key}")
                actual[key]=result.stdout.strip()
            if actual["user.name"]!=profile["git_name"] or actual["user.email"]!=profile["email"]:
                raise RuntimeError("Git identity verification failed.")
            self.gitstatus.config(text=f"Verified for {repo}: {actual['user.name']} <{actual['user.email']}>")
            messagebox.showinfo("Git identity applied",f"Verified successfully.\n\nRepository: {repo}\nName: {actual['user.name']}\nEmail: {actual['user.email']}\n\nBackup: {backup}\nSSH host aliases are managed separately.")
        except Exception as e:
            # Restore the repository config if application or verification failed.
            try:
                if 'rollback_copy' in locals() and rollback_copy.is_file() and 'config_path' in locals():
                    shutil.copy2(rollback_copy,config_path)
            except OSError:
                pass
            messagebox.showerror("Could not apply Git identity",str(e))

    def _apply_workspace_git_configuration(self, profiles, assigned):
        if not messagebox.askyesno("Apply configuration","Back up current config, then update managed sections in ~/.gitconfig and ~/.ssh/config? Existing unmanaged content will be preserved."):
            return
        try:
            backup=self.backup.create()
            includes=[]
            for p in profiles:
                pf=PROFILE_DIR/(p["id"]+".gitconfig")
                atomic_write(pf,f'[user]\n\tname = {p["git_name"]}\n\temail = {p["email"]}\n',0o600)
            for w in assigned:
                p=next((x for x in profiles if x["id"]==w["git_profile_id"]),None)
                if not p:continue
                path=str(Path(w["path"]).expanduser().resolve())
                if not path.endswith("/"):path+="/"
                includes.append(f'[includeIf "gitdir:{path}**"]\n\tpath = {PROFILE_DIR/(p["id"]+".gitconfig")}')
            gitblock=GIT_BEGIN+"\n"+"\n".join(includes)+"\n"+GIT_END
            SafeConfigEditor.replace_block(HOME/".gitconfig",GIT_BEGIN,GIT_END,gitblock)
            sshlines=[SSH_BEGIN]
            for p in profiles:
                if p["auth"]!="ssh":continue
                key=Path(p["key_path"]).expanduser()
                sshlines += [f"Host {p['host_alias']}",f"    HostName {p['host']}",f"    User git",f"    IdentityFile {key}", "    IdentitiesOnly yes",""]
            sshlines.append(SSH_END)
            if any(p["auth"]=="ssh" for p in profiles):
                SafeConfigEditor.replace_block(HOME/".ssh"/"config",SSH_BEGIN,SSH_END,"\n".join(sshlines))
                os.chmod(HOME/".ssh",0o700)
            self.gitstatus.config(text=f"Applied workspace Git/SSH configuration. Backup: {backup}")
            messagebox.showinfo("Applied",f"Workspace Git conditional includes and SSH host aliases updated.\nBackup: {backup}\n\nFor SSH remotes, use the generated Host alias, e.g. git@github-work:owner/repo.git.\nFor HTTPS, use a secure credential helper; no token/password was saved.")
        except Exception as e:
            messagebox.showerror("Could not apply",str(e))

if __name__=="__main__":
    App().mainloop()
