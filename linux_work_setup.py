#!/usr/bin/env python3
"""DevPilot — Linux development environment manager (preview)."""
from __future__ import annotations
import json, os, shlex, shutil, subprocess, threading, uuid
from pathlib import Path
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

APP_VERSION="0.2.0-preview"
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
    def create(self):
        dest=BACKUP_DIR/datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        dest.mkdir(parents=True,exist_ok=False)
        items=[]
        for rel in self.TARGETS+[".config/linux-work-setup/config.json"]:
            src=HOME/rel; item={"path":rel,"exists":src.is_file(),"copied":False}
            if src.is_file():
                out=dest/rel; out.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(src,out); item["copied"]=True
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

class App(tk.Tk):
    def __init__(self):
        super().__init__(); self.title("DevPilot — v"+APP_VERSION)
        self.geometry("1080x740"); self.minsize(900,620)
        self.cfg=Config(); self.backup=Backup(); self.pkgmap={}
        self.agent_rows={}; self.agent_busy=False
        self._ui(); self.refresh_packages(); self.refresh_workspaces(); self.refresh_profiles(); self.refresh_agents()
    def _ui(self):
        style=ttk.Style(self)
        try:style.theme_use("clam")
        except tk.TclError:pass
        h=ttk.Frame(self,padding=14);h.pack(fill="x")
        ttk.Label(h,text="DevPilot",font=("Sans",17,"bold")).pack(anchor="w")
        ttk.Label(h,text="Development Setup • Project Workspaces • Git identities • AI terminal agents",foreground="#555").pack(anchor="w")
        self.tabs=ttk.Notebook(self);self.tabs.pack(fill="both",expand=True,padx=12,pady=(0,12))
        self.dev=ttk.Frame(self.tabs,padding=10);self.ws=ttk.Frame(self.tabs,padding=10)
        self.git=ttk.Frame(self.tabs,padding=10);self.agents=ttk.Frame(self.tabs,padding=10)
        self.back=ttk.Frame(self.tabs,padding=10)
        for frame,label in [(self.dev,"Development Setup"),(self.ws,"Project Workspaces"),(self.git,"Git Accounts & SSH"),(self.agents,"AI Agents"),(self.back,"Backup & Recovery")]:
            self.tabs.add(frame,text=label)
        self._dev_ui();self._ws_ui();self._git_ui();self._agents_ui();self._backup_ui()
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
        ttk.Label(self.ws,text="A profile assigned to a workspace applies to repositories under that directory through Git conditional includes. Repository-local Git settings remain untouched.",wraplength=900,foreground="#555").pack(anchor="w",pady=10)
    def _git_ui(self):
        ttk.Label(self.git,text="Git profiles",font=("Sans",13,"bold")).pack(anchor="w")
        self.gitt=ttk.Treeview(self.git,columns=("name","email","auth","alias"),show="headings",height=9)
        for c,t,w in [("name","Profile / Git name",220),("email","Commit email",260),("auth","Authentication",130),("alias","SSH host alias",220)]:
            self.gitt.heading(c,text=t);self.gitt.column(c,width=w)
        self.gitt.pack(fill="both",expand=True,pady=8)
        row=ttk.Frame(self.git);row.pack(fill="x")
        ttk.Button(row,text="Add Git account",command=self.add_profile).pack(side="left")
        ttk.Button(row,text="Edit selected",command=self.edit_profile).pack(side="left",padx=6)
        ttk.Button(row,text="Remove selected",command=self.remove_profile).pack(side="left")
        ttk.Button(row,text="Generate SSH key",command=self.generate_key).pack(side="left",padx=6)
        ttk.Button(row,text="Apply Git / SSH configuration",command=self.apply_git).pack(side="left")
        ttk.Label(self.git,text="SSH: each account gets a distinct key and Host alias (for example github-work). HTTPS: DevPilot does not store tokens or passwords; configure a secure Git credential manager separately.",wraplength=930,foreground="#555").pack(anchor="w",pady=10)
        self.gitstatus=ttk.Label(self.git,text="No changes applied yet.",foreground="#555");self.gitstatus.pack(anchor="w")
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
                 "printf '\\n\\nAgent exited with code %s.\\n' \"$rc\"; "
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
            self.gitt.insert("","end",iid=p["id"],values=(p["name"],p["email"],p["auth"],p.get("host_alias","")))
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
    def apply_git(self):
        profiles=self.cfg.data["git_profiles"]
        assigned=[w for w in self.cfg.data["workspaces"] if w.get("git_profile_id")]
        if not profiles or not assigned:messagebox.showinfo("Nothing to apply","Add Git profiles and assign at least one workspace.");return
        if not messagebox.askyesno("Apply configuration","Back up current config, then update managed sections in ~/.gitconfig and ~/.ssh/config? Existing unmanaged content will be preserved."):return
        try:
            backup=self.backup.create()
            # Build isolated profile config files and includeIf directives.
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
            self.gitstatus.config(text=f"Applied. Backup: {backup}")
            messagebox.showinfo("Applied",f"Git conditional includes and SSH host aliases updated.\nBackup: {backup}\n\nFor SSH remotes, use the generated Host alias, e.g. git@github-work:owner/repo.git.\nFor HTTPS, use a secure credential helper; no token/password was saved.")
        except Exception as e:messagebox.showerror("Could not apply",str(e))

if __name__=="__main__":
    App().mainloop()
