import pickle

from cpgqls_client import *
import json

import os
import igraph
import sys
import re
import multiprocessing
import datetime



def print_process(name, now, sum):  # 打印进度条
    print("\r", end="")
    print(f"{name} progress: {now}/{sum} {now*100 // sum}% ", "▋" * (now*100 // sum//2), end="")
    sys.stdout.flush()


def joern_parse(joern_parse_dir, indir, outdir):
    # indir是源代码目录，joern会解析该目录下的所有源文件
    # joern_parse_dir是joern-parse所在的目录，一般为joern根目录
    # outdir是解析生成的bin文件的目录

    # if os.path.exists(outdir):  # 表明之前解析过,主要用于进行多批解析
    #     print("----- warning:the bin file exists!-----")
    #     # print(outdir+" exists!")
    #     return
    ret = os.system(f'sh {joern_parse_dir} {indir} -o {outdir}')
    if ret == 0:
        print("joern_parse progress: {}%: ".format(100), "▋" * 50)
    else:
        print("-----joern parsing failed!-----")
        sys.exit(0)


def connect_server():
    # 和joern server连接，需提前运行./joern --server
    # 返回值为一个client对象，用于之后与joern server进行交互
    # 端口和用户名密码可修改，参照https://docs.joern.io/server
    server_endpoint = "localhost:8080"
    basic_auth_credentials = ("username", "password")
    client = CPGQLSClient(server_endpoint, auth_credentials=basic_auth_credentials)
    return client


def import_souce(client, file_path):
    # file_path为需要导入的bin文件路径
    # 该函数执行完之后，cpg被加载进joern server

    query = f'importCpg(\"{file_path}\")'
    try:
        result = client.execute(query)
        if result['stderr'].find('java') != -1:
            print('joern server error:'+result['stderr'])
            sys.exit(0)
        else:
            print("import_souce progress: {}%: ".format(100), "▋" * 50)
    except Exception as e:
        print("-----import souce nodes failed!-----")
        print(e)
        sys.exit(0)
    # query = 'run.ossdataflow' 一般来说，使用joern-parse生成bin文件之后，数据流处理自动完成，如果在运行时出问题，可再运行下面的指令
    # result = client.execute(query)
    # print(result['stdout'])


def get_all_nodes(client, node_list_path):
    # node_list_path 存储所有结点的文件路径
    # 该函数返回一个字典，格式:{func_id:{id:node}}
    query = f"cpg.method.filter(node=>node.filename.contains(\"{raw_dir}\"))\
    .filterNot(node => node.name.contains(\"<\"))\
    .filterNot(node => node.lineNumber==node.lineNumberEnd)\
    .filterNot(node => node.lineNumber==None)\
    .filterNot(node => node.lineNumberEnd==None)\
    .filterNot(node => node.columnNumber==None)\
    .filterNot(node => node.columnNumberEnd==None)\
    .map(node => List(node.id,node.ast.l)).toJson  |>\"{node_list_path}\""
    try:
        result = client.execute(query)
        # print('client:'+result['stderr'])
        if result['stderr'].find('java') != -1:
            print('joern server error:'+result['stderr'])
            sys.exit(0)
        with open(node_list_path)as f:
            node_list = json.load(f)

        m2id2node = dict()  # 该字典使用id作为key,对应结点信息作为内容
        i = 1
        for tup in node_list:
            func_id = str(tup[0])
            id2node = dict()
            for node in tup[1]:
                node['id'] = str(node['id'])
                id2node[node['id']] = node
            m2id2node[func_id] = id2node
            print_process('get_all_nodes', i, len(node_list))
            i += 1

        print("\r")
        return m2id2node

    except Exception as e:
        print("-----getting all nodes failed!-----")
        print(e)
        sys.exit(0)


def get_all_dotfile(client, raw_dir, dotfile_path):
    # raw_dir 源代码目录，用来过滤库函数
    # dotpdg_path 生成的存储dot文件的json文件路径
    # 该函数返回一个列表：[[func_id,func_pdg_str,func_ast_str]

    query = f"cpg.method.filter(node=>node.filename.contains(\"{raw_dir}\"))\
    .filterNot(node => node.name.contains(\"<\"))\
    .filterNot(node => node.lineNumber==node.lineNumberEnd)\
    .filterNot(node => node.lineNumber==None)\
    .filterNot(node => node.lineNumberEnd==None)\
    .filterNot(node => node.columnNumber==None)\
    .filterNot(node => node.columnNumberEnd==None)\
    .map(node => List(node.id,node.dotPdg.l,node.dotAst.l)).toJson |>\"{dotfile_path}\""

    try:
        result = client.execute(query)
        if result['stderr'].find('java') != -1:
            print('joern server error:'+result['stderr'])
            sys.exit(0)

        with open(dotfile_path)as f:
            dot_list = json.load(f)
        return dot_list

    except Exception as e:
        print("-----getting all dot file failed!-----")
        print(e)
        sys.exit(0)


def get_all_callee(client, raw_dir, callee_path):
    # callee_path 是存储callee信息的json文件路径
    # 该函数返回一个字典，{func_id:{caller_id:calleeid}}
    query = f"cpg.method.filter(node=>node.filename.contains(\"{raw_dir}\"))\
    .filterNot(node => node.name.contains(\"<\"))\
    .filterNot(node => node.lineNumber==node.lineNumberEnd)\
    .filterNot(node => node.lineNumber==None)\
    .filterNot(node => node.lineNumberEnd==None)\
    .filterNot(node => node.columnNumber==None)\
    .filterNot(node => node.columnNumberEnd==None)\
    .map(node=>List(node.id,node.call.filterNot(node => node.name.contains(\"<\")).map(c => List(c.id,c.callee.id.l)).l)).toJson |>\"{callee_path}\""
    # print(query)
    try:
        result = client.execute(query)
        if result['stderr'].find('java') != -1:
            print('joern server error:'+result['stderr'])
            sys.exit(0)

        with open(callee_path)as f:
            callee_list = json.load(f)
        m2callee_dict = dict()
        i = 1
        for tup in callee_list:
            func_id = str(tup[0])
            callee_dict = dict()
            for tup2 in tup[1]:
                callsite_id = str(tup2[0])
                callee_id = str(tup2[1][0])
                callee_dict[callsite_id] = callee_id
            m2callee_dict[func_id] = callee_dict
            print_process('get_all_callee', i, len(callee_list))
            i += 1
        print("\r")
        return m2callee_dict

    except Exception as e:
        print("-----getting all callee failed!-----")
        print(e)
        sys.exit(0)


def get_all_callIn(client, raw_dir, callIn_path, call_info_dir):
    # raw_dir是源代码目录，是为了筛选在源代码目录里的method
    # callIn_path是产生的中间文件的路径
    # 该函数返回一个字典，字典的内容格式：{funcid:[[调用该函数的函数id,调用发生的结点id]]}
    # 存在funcid对应的内容为空的情况，即{funcid:[]}

    query = f"cpg.method.filter(node=>node.filename.contains(\"{raw_dir}\"))\
    .filterNot(node => node.name.contains(\"<\"))\
    .filterNot(node => node.lineNumber==node.lineNumberEnd)\
    .filterNot(node => node.lineNumber==None)\
    .filterNot(node => node.lineNumberEnd==None)\
    .filterNot(node => node.columnNumber==None)\
    .filterNot(node => node.columnNumberEnd==None)\
    .map(c =>List(c.id,c.callIn.map(d => List(d.method.id,d.id)).l)).toJson |>\"{callIn_path}\""
    # print(query)
    # 筛选raw文件夹中的函数、筛选掉函数名中包含<的（一般为joern自己加的）、函数声明结点（即行开始和结束号相同的）、函数行列号不存在的
    try:
        result = client.execute(query)
        if result['stderr'].find('java') != -1:
            print('joern server error:'+result['stderr'])
            sys.exit(0)
        with open(callIn_path)as f:
            callIn_list = json.load(f)
        callIn_dict = dict()
        for i in range(len(callIn_list)):
            list_t = callIn_list[i]
            func_id = str(list_t[0])
            for j in range(len(list_t[1])):
                list_t[1][j] = [str(id) for id in list_t[1][j]]
            callIn_dict[func_id] = list_t[1]
            print_process('get_all_callIn', i+1, len(callIn_list))

        call_info_file = call_info_dir+"/callIn_dict.pkl"
        with open(call_info_file, "wb+")as f1:
            pickle.dump(callIn_dict, f1)
        print("\r")
        return callIn_dict

    except Exception as e:
        print("-----getting all callIn failed!-----")
        print(e)
        sys.exit(0)


def generate_prop_for_node(node):
    # 为每一个结点创建属性字典，funcid是该结点所在的函数的结点id，node是id2node中包含结点全部信息的字典
    # 每个结点记录funcid、code、lineNumber、lineNumberEnd、columnNumber、columnNumberEnd、id、_label、callee_id等信息
    prop = dict()

    properties = ['funcid', 'code', 'lineNumber', 'lineNumberEnd', 'columnNumber',
                  'columnNumberEnd', 'id', '_label', 'callee_id', 'typeFullName', 'name', 'filename']
    for key in properties:
        if key in node:
            prop[key] = node[key]
        else:
            prop[key] = None
    prop['Name'] = prop.pop('name')  # 因为igraph加入键值的时候会默认有一个'name',所以改成'Name'
    return prop


def get_all_local_param_2_identifier(client, local2identifier_path, type):
    # 获得所有local和parameter结点对应的identifier结点
    # local2identifier_path是临时文件的存储路径
    # 该函数返回一个字典，其格式如下：{func_id:{local_id/para_id:[identifier_id]}}
    # 存在key值对应字典为空的情况，即{func_id:{}}，使用时需注意
    query = f"cpg.method.filter(node=>node.filename.contains(\"{raw_dir}\"))\
    .filterNot(node => node.name.contains(\"<\"))\
    .filterNot(node => node.lineNumber==node.lineNumberEnd)\
    .filterNot(node => node.lineNumber==None)\
    .filterNot(node => node.lineNumberEnd==None)\
    .filterNot(node => node.columnNumber==None)\
    .filterNot(node => node.columnNumberEnd==None)\
    .map(c =>List(c.id,c.{type}.map(d =>List(d.id,d.referencingIdentifiers.id.l)).l)).toJson |>\"{local2identifier_path}\""
    try:
        result = client.execute(query)
        if result['stderr'].find('java') != -1:
            print('joern server error:'+result['stderr'])
            sys.exit(0)
        with open(local2identifier_path)as f:
            m2l2i_list = json.load(f)
        m2l2i_dict = dict()

        for i in range(len(m2l2i_list)):  # 列表中每一个元素是一个只有一个键值的字典
            m2l2i = m2l2i_list[i]
        # for m2l2i in m2l2i_list:
            func_id = str(m2l2i[0])
            l2i_dict = dict()
            l2i_list = m2l2i[1]
            for l2i in l2i_list:
                local_id = str(l2i[0])
                l2i[1] = [str(identifier_id) for identifier_id in l2i[1]]
                l2i_dict[local_id] = l2i[1]
            m2l2i_dict[func_id] = l2i_dict
            print_process(f'get_all_{type}_identifier', i+1, len(m2l2i_list))

        print("\r")
        return m2l2i_dict

    except Exception as e:
        print(f"-----getting all method_{type}_identifier failed!-----")
        print(e)
        sys.exit(0)


def draw_graph(func_id, nodes, edges, id2node, callee_dict, type):
    # func_id：函数id
    # nodes：结点id的列表
    # edges：边的列表，[[start_id,end_id,label]]其中label仅存储CDG或DDG，AST边一般为''
    # id2node：所有结点的列表
    # callee_dict：存储callee信息的字典
    # type：标识pdg或ast
    # 该函数返回一个igraph对象
    filename = id2node[func_id]['filename']

    if len(nodes) == 0:
        return -1
    g = igraph.Graph(directed=True)

    # 加入所有结点
    for id in nodes:
        id2node[id]['funcid'] = func_id  # 为所有结点加入它所在函数的id
        id2node[id]['filename'] = filename  # 为所有结点加入它所在的文件名

        if type == 'pdg':  # pdg中需加入callee信息
            if id in callee_dict:
                id2node[id]["callee_id"] = callee_dict[id]
            id2node[id]['IsPdgNode'] = True
        prop = generate_prop_for_node(id2node[id])
        if type == 'ast':
            if'IsPdgNode' in id2node[id]:
                prop['IsPdgNode'] = id2node[id]['IsPdgNode']
            else:
                prop['IsPdgNode'] = False

        g.add_vertex(id, **prop)

    # 加入所有边
    for edge in edges:
        label = {'label': edge[2]}
        g.add_edge(edge[0], edge[1], **label)

    return g


# 使用前需保证l2i_dict不为空，即函数存在local结点
def add_lp_to_pdg(func_id, pdg, ast, lp2i_dict, id2node):
    # func_id:函数id
    # pdg,ast:对应的pdg和ast的igraph对象
    # l2i_dict:local对应的identifier列表 格式{local_id/para_id:[identifier_id]}
    # id2node:所有结点的列表
    # 该函数将local结点加入pdg并加上相应的边
    edge_prop = {'label': 'DDG'}
    for lp_id in lp2i_dict:
        identifier_list = lp2i_dict[lp_id]
        if len(identifier_list) == 0:  # 如果该local或parameter没有引用，则直接跳到下一个
            continue
        if id2node[lp_id]['_label'] == "LOCAL":  # 如果是parameter，已经在pdg中了,因此只需加入local结点
            prop = generate_prop_for_node(id2node[lp_id])
            pdg.add_vertex(lp_id, **prop)
            local_node = ast.vs.find(lp_id)
            local_node['IsPdgNode'] = True
            # edge_prop={'label': 'DDG'}
            pdg.add_edge(func_id, lp_id, **edge_prop)
        for identifier_id in identifier_list:
            identifier_node = ast.vs.find(id=identifier_id)
            candidate_node = identifier_node
            find = False
            while find == False:
                if candidate_node['IsPdgNode'] == True:
                    end_id = candidate_node['id']
                    find = True
                else:
                    if candidate_node['_label'] == 'METHOD':  # 找到method结点,即ast的根节点
                        break
                    else:
                        candidate_node = candidate_node.predecessors()[0]  # 继续向上找
            if find:
                if pdg.are_connected(lp_id, end_id) == False:
                    pdg.add_edge(lp_id, end_id, **edge_prop)


def mydot_parser(dot_str):
    # dot_str：原始的dot文件字符串
    # 仅提取边集，且对于边的label仅提取CDG或DDG
    # 使用提取的边集获得点集
    re_pattern = re.compile(
        r'"([0-9]+)" -> "([0-9]+)"(?:  \[ label = "([C|D]DG):[\s\S]*?"\])*')

    ret = re_pattern.findall(dot_str)

    node_list = set()
    edge_list = ret
    for matched in ret:
        node_list.add(matched[0])
        node_list.add(matched[1])
    return node_list, edge_list

def store_pdg_ast(func_file_path,func_name,func_id,pdg,ast,graph_db_dir):
    #func_file_path 源代码路径
    # func_name 函数名
    # func_id 函数id

    func_file_dir, func_file_name = os.path.split(func_file_path) #分离获得文件的目录
    index = len(graph_db_dir)-len("graph_db")+len("raw") #获得raw文件夹之后的路径在字符串中的起点
    dir_list=func_file_path[index:].split('/')#列表中第一个为空，第二个为raw的子目录。

    pkl_dir = graph_db_dir+'/'+dir_list[1]
    pressed_path=dir_list[2]
    for i in range(3,len(dir_list)):#压缩后续目录为一个目录，目录名用_连接
        pressed_path=pressed_path+'_'+pkl_dir[i]
    pkl_dir=pkl_dir+pressed_path

    pdg_pkl_dir = f"{pkl_dir}/pdg"
    ast_pkl_dir = f"{pkl_dir}/ast"
    if os.path.exists(pdg_pkl_dir) == False:
        os.makedirs(pdg_pkl_dir)
    pdg_file_path = pdg_pkl_dir+f"/{func_name}_{func_id}.pkl"
    # print(pdg_file_path)
    with open(pdg_file_path, "wb+")as f1:
        pickle.dump(pdg, f1)
    if os.path.exists(ast_pkl_dir) == False:
        os.makedirs(ast_pkl_dir)
    ast_file_path = ast_pkl_dir+f"/{func_name}_{func_id}.pkl"
    # print(pdg_file_path)
    with open(ast_file_path, "wb+")as f1:
        pickle.dump(ast, f1)

def multi_process_complete_graph(para_list):
    # 多进程函数，用来完善每个函数的pdg
    func_id, pdg_str, ast_str, id2node, callee_dict, graph_db_dir, lp2i_dict = para_list
    pdg_nodes, pdg_edges = mydot_parser(pdg_str)
    pdg = draw_graph(func_id, pdg_nodes, pdg_edges, id2node, callee_dict, "pdg")
    if pdg == -1:
        return
    ast_nodes, ast_edges = mydot_parser(ast_str)
    ast = draw_graph(func_id, ast_nodes, ast_edges, id2node, callee_dict, "ast")

    add_lp_to_pdg(func_id, pdg, ast, lp2i_dict, id2node)

    # pdg.es["curved"] = False  # 解决Attribute does not exist问题
    # igraph.plot(pdg, vertex_label=pdg.vs['code'])
    func_file_path = id2node[func_id]['filename']
    func_name = id2node[func_id]['name']
    store_pdg_ast(func_file_path,func_name,func_id,pdg,ast,graph_db_dir)


def complete_graph(dot_list, m2id2node, m2callee_dict, graph_db_dir, m2lp2i_dict):
    # pdg_dict,ast_dict 存储pdg和ast的dot文件的字典
    # id2node 存储所有结点信息的字典
    # callee_dict 存储所有callee信息的字典
    # graph_db_dir 存储生成的pdg、ast信息的目录
    # 每个pdg生成一个igraph对象并存储在pkl文件中，对于pdg中的call结点，还会记录其callee信息，最终每个pkl的文件名为funcname_funcid
    # 每个ast文件同样如此
    try:
        i = 1
        multi_para_list = list()
        with multiprocessing.Pool(8)as p:
            for dot in dot_list:
                func_id = str(dot[0])
                pdg_str = dot[1][0]
                ast_str = dot[2][0]
                id2node = m2id2node[func_id]
                callee_dict = m2callee_dict[func_id]
                lp2i_dict = m2lp2i_dict[func_id]
                multi_para_list.append([func_id, pdg_str, ast_str, id2node, callee_dict, graph_db_dir, lp2i_dict])
            ret_list = p.imap_unordered(multi_process_complete_graph, multi_para_list)
            for ret in ret_list:
                print_process('complete_graph', i, len(multi_para_list))
                i += 1

        print('\r')
        # print(f"-----completing pdg、ast successfully!-----")
    except Exception as e:
        print(f"-----completing pdg、ast failed!-----")
        print(e)
        sys.exit(0)


if __name__ == '__main__':
    # 所有结点id以字符串形式存储，这是因为从dot文件中解析出来的id是字符串形式的
    joern_parse_dir = '/home/wanghu/new_joern/v1_1_609/joern-parse'  # 需根据自己的环境进行修改

    cwd_dir = os.getcwd()
    raw_dir = cwd_dir+"/raw"  # 源文件目录,需手动创建

    # 中间文件目录，包括bin文件、pdg dot、calllee信息和所有结点的json文件
    intermediate_dir = cwd_dir+"/intermediate"

    if(os.path.exists(intermediate_dir) == False):
        os.mkdir(intermediate_dir)
    graph_db_dir = cwd_dir+"/graph_db"  # 该文件夹用来存储最终生成的pdg和ast
    if os.path.exists(graph_db_dir) == False:
        os.mkdir(graph_db_dir)
    bin_path = intermediate_dir+"/cpg.bin"  # bin文件路径
    joern_parse(joern_parse_dir, raw_dir, bin_path)  # 生成bin文件

    client = connect_server()  # 需提前运行./joern --server
    import_souce(client, bin_path)  # 导入bin文件到服务器

    call_info_dir = cwd_dir+"/call_info"  # 该文件夹用来存储callIn信息
    if(os.path.exists(call_info_dir) == False):
        os.mkdir(call_info_dir)
    callIn_path = intermediate_dir+"/callIn.json"  # 存储callIn信息的json文件
    callIn_dict = get_all_callIn(client, raw_dir, callIn_path, call_info_dir)

    callee_list_path = intermediate_dir+"/callee.json"  # 存储callee信息的json文件
    m2callee_dict = get_all_callee(client, raw_dir, callee_list_path)

    m2l2i_path = intermediate_dir+"/m2l2i.json"
    m2l2i_dict = get_all_local_param_2_identifier(client, m2l2i_path, "local")
    m2p2i_path = intermediate_dir+"/m2p2i.json"
    m2p2i_dict = get_all_local_param_2_identifier(client, m2p2i_path, "parameter")

    # 将local和parameter合并
    for func_id in m2l2i_dict:
        if func_id in m2p2i_dict:
            m2l2i_dict[func_id].update(m2p2i_dict[func_id])

    node_list_path = intermediate_dir + "/allnodes.json"  # 存储所有结点的json文件
    m2id2node = get_all_nodes(client, node_list_path)

    dot_list_path = intermediate_dir+"/dot.json"  # 存储所有 pdg dot的json文件

    dot_list = get_all_dotfile(client, raw_dir, dot_list_path)
    t1 = datetime.datetime.now()

    # 根据以上信息生成igraph形式的pdg、ast,并按照源代码目录结构存储
    complete_graph(dot_list, m2id2node, m2callee_dict, graph_db_dir, m2l2i_dict)

    t2 = datetime.datetime.now()
    print((t2-t1).seconds)

    # joern_parse(joern_parse_dir,raw_dir,bin_path)