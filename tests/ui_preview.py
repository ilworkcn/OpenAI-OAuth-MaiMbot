"""本机页面验收，示例账号与模型结果仅用于检查界面操作。"""
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

SCRIPT = r"""<script>
const demo={accounts:{active_client_id:null,accounts:[]},login:{status:'idle',message:'界面预览 · 使用示例账号检查按钮和排版。'},models:[],test:{status:'idle'},enabled:true,data_dir:'/MaiMBot/data/plugins/ilworkcn.openai-oauth',request_timeout:240};
const host={models:[],tasks:[{id:'replyer',label:'聊天回复',models:['原有模型']},{id:'planner',label:'行为规划',models:['原有模型']}]};
window.maibot={query:async(name)=>structuredClone(name==='host_models'?host:demo),action:async(name,args={})=>{
if(name==='login'){demo.login={status:'waiting',message:'界面预览：请使用示例回调地址。',url:'https://example.com/oauth-preview',expires_at:Date.now()/1000+600}}
if(name==='callback'){demo.accounts={active_client_id:'example-account',accounts:[{client_id:'example-account',name:'示例账号',connected:true,plan_enabled:true}]};demo.login={status:'connected',message:'示例账号已连接。'}}
if(name==='cancel')demo.login={status:'idle',message:'已取消。'};
if(name==='models')demo.models=[{slug:'example-model',display_name:'示例聊天模型'}];
if(name==='test'){demo.test={status:'running',model:args.model,started_at:Date.now()/1000};setTimeout(()=>{demo.test={...demo.test,status:'success',seconds:1.2,text:'麦麦，连接成功。（页面示例）'}},1200)}
if(name==='add_model'){const m={name:'chatgpt-'+args.model,model_identifier:args.model,extra_params:args.effort?{reasoning:{effort:args.effort}}:{}};host.models=[m];return {name:m.name,message:'示例模型已添加，模拟重载完成。'}}
if(name==='assign_tasks'){for(const t of host.tasks)if(args.tasks.includes(t.id))t.models=[args.model_name];return {message:'示例任务已更新，模拟重载完成。'}}
if(name==='example')return {text:'[[api_providers]]\nname = "ChatGPT-OAuth"\nclient_type = "openai_oauth_maimbot"\nauth_type = "none"\n\n[[models]]\nmodel_identifier = "example-model"'};
return {message:'页面示例已完成'};
}};
</script>"""

class Preview(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != '/':
            self.send_error(404)
            return
        html = (Path(__file__).resolve().parents[1] / 'webui/account.html').read_text('utf-8')
        data = html.replace('<script type="module">', SCRIPT+'<script type="module">').encode()
        self.send_response(200)
        self.send_header('Content-Type','text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(data)

if __name__ == '__main__':
    HTTPServer(('127.0.0.1',18765), Preview).serve_forever()
