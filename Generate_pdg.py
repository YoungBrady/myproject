
import pickle

from cpgqls_client import *
import json

import os
import glob
from igraph import *
import pydot


def joern_parse(joern_parse_dir, indir, outdir):
    # indir是源代码目录，joern会解析该目录下的所有源文件
    # joern_parse_dir是joern-parse所在的目录，一般为joern根目录
    # outdir是解析生成的bin文件的目录

    if os.path.exists(outdir):  # 表明之前解析过,主要用于进行多批解析
        print("----- warning:the bin file exists!-----")
        # print(outdir+" exists!")
        return
    print(f'sh {joern_parse_dir} {indir} -o {outdir}')
    ret = os.system(f'sh {joern_parse_dir} {indir} -o {outdir}')
    if ret == 0:
        print("-----joern parsing successfully!-----")
    else:
        print("-----joern parsing failed!-----")
        sys.exit(0)


def connect_server():
    # 和joern server连接，需提前运行./joern --server
    # 返回值为一个client对象，用于之后与joern server进行交互
    # 端口和用户名密码可修改，参照https://docs.joern.io/server
    server_endpoint = "localhost:8080"
    basic_auth_credentials = ("username", "password")
    client = CPGQLSClient(
        server_endpoint, auth_credentials=basic_auth_credentials)
    return client


def import_souce(client, file_path):
    # file_path为需要导入的bin文件路径
    # 该函数执行完之后，cpg被加载进joern server

    # query = open_query(file_path) 考虑兼容性，使用下面的查询指令
    query = f'importCpg(\"{file_path}\")'
    try:
        result = client.execute(query)
        print("-----importing code successfully!-----")
    except Exception as e:
        print("-----importing code failed!-----")
        print(e)
        sys.exit(0)

    # query = 'run.ossdataflow' 一般来说，使用joern-parse生成bin文件之后，数据流处理自动完成，如果在运行时出问题，可再运行下面的指令
    # result = client.execute(query)
    # print(result['stdout'])


def get_all_nodes(client, node_list_path):
    # node_list_path 存储所有结点的文件路径
    # 该函数返回一个字典，其key为结点id，内容为joern导出的对应结点信息的字典
    query = f"cpg.all.toJson |>\"{node_list_path}\""
    # print(query)
    try:
        result = client.execute(query)
        with open(node_list_path)as f:
            node_list = json.load(f)
        id2node = dict()  # 该字典使用id作为key,对应结点信息作为内容
        for node in node_list:
            id2node[str(node['id'])] = node

        print("-----getting all nodes successfully!-----")
        return id2node

    except Exception as e:
        print("-----getting all nodes failed!-----")
        print(e)
        sys.exit(0)
    # # print(method_list[0])


def get_all_dotfile(client, raw_dir, dotfile_path, id2node):
    # raw_dir 源代码目录，用来过滤库函数的pdg
    # dotpdg_path 生成的存储dot文件的json文件路径
    # 该函数返回个字典，key:函数id 内容：该函数的pdg dot

    query = f"cpg.method.filter(node=>node.filename.contains(\"{raw_dir}\")).map(node => (node.id,node.dotPdg.toJson,node.dotAst.toJson)).toJson |>\"{dotfile_path}\""
    # query = f"cpg.method.map(c => (c.id,c.dotPdg.toJson)).toJson |>\"{dotpdg_path}\""
    # print(query)
    try:
        result = client.execute(query)
        with open(dotfile_path)as f:
            dot_list = json.load(f)
        pdg_dict = dict()
        ast_dict = dict()
        # i = 0
        for dot in dot_list:
            func_id = str(dot['_1'])
            if ('columnNumber' in id2node[func_id]) == False or ('lineNumber' in id2node[func_id]) == False:
                continue  # 过滤没有行号或列号的函数的pdg或ast
            dotpdg_str = json.loads(dot['_2'])[0]
            dot_pdg = pydot.graph_from_dot_data(dotpdg_str)[0]
            dotast_str = json.loads(dot['_3'])[0]
            dot_ast = pydot.graph_from_dot_data(dotast_str)[0]
            if dot_pdg != None:
                pdg_dict[func_id] = dot_pdg
            if dot_ast != None:
                ast_dict[func_id] = dot_ast
            # print(func_id)
            # i+=1
            # if i>100:break
        print("-----getting all dot file successfully!-----")
        return pdg_dict, ast_dict

    except Exception as e:
        print("-----getting all dot file failed!-----")
        print(e)
        sys.exit(0)


def get_all_callee(client, callee_path):
    # callee_path 是存储callee信息的json文件路径
    # 该函数返回一个字典，key:caller id 内容callee id
    query = f"cpg.call.map(c => (c.id,c.callee.id.toJson)).toJson |>\"{callee_path}\""
    # print(query)
    try:
        result = client.execute(query)
        with open(callee_path)as f:
            callee_list = json.load(f)
        callee_dict = dict()
        for tup in callee_list:
            id = tup['_1']
            callee_id = json.loads(tup['_2'])[0]
            callee_dict[str(id)] = str(callee_id)
        print("-----getting all callee successfully!-----")
        return callee_dict

    except Exception as e:
        print("-----getting all callee failed!-----")
        print(e)
        sys.exit(0)


def get_all_callIn(client, raw_dir, callIn_path):
    # raw_dir是源代码目录，是为了筛选在源代码目录里的method
    # callIn_path是产生的中间文件的路径
    # 该函数返回一个字典，字典的内容格式：{funcid:[(调用该函数的函数id,调用发生的结点id)]}
    # 仅记录了被其他函数调用的函数的信息

    query = f"cpg.method.filter(node=>node.filename.contains(\"{raw_dir}\")).map(c =>(c.id,c.callIn.map(d => (d.method.id,d.id)).toJson)).toJson |>\"{callIn_path}\""
    # print(query)
    try:
        result = client.execute(query)
        with open(callIn_path)as f:
            callIn_list = json.load(f)
        callIn_dict = dict()
        for tup in callIn_list:
            id = tup['_1']
            callIn_list_t = json.loads(tup['_2'])
            if len(callIn_list_t) != 0:
                # print(callIn_list_t)
                callIn_list = list()
                for callIn_dict_t in callIn_list_t:
                    callIn_list.append(
                        (str(callIn_dict_t['_1$mcJ$sp']), str(callIn_dict_t['_2$mcJ$sp'])))
                callIn_dict[str(id)] = callIn_list
            # callee_dict[str(id)] = str(callee_id)
        print("-----getting all callIn successfully!-----")
        return callIn_dict

    except Exception as e:
        print("-----getting all callIn failed!-----")
        print(e)
        sys.exit(0)


def generate_prop_for_node(funcid, node):
    # 为每一个结点创建属性字典，funcid是该结点所在的函数的结点id，node是id2node中包含结点全部信息的字典
    # 每个结点记录funcid、code、lineNumber、lineNumberEnd、columnNumber、columnNumberEnd、id、_label、callee_id等信息
    prop = dict()
    prop['funcid'] = funcid
    if 'code' in node:
        prop['code'] = node['code']
    else:
        prop['code'] = None

    if 'lineNumber' in node:
        prop['lineNumber'] = node['lineNumber']
    else:
        prop['lineNumber'] = None

    if 'lineNumberEnd' in node:
        prop['lineNumberEnd'] = node['lineNumberEnd']
    else:
        prop['lineNumberEnd'] = None

    if 'columnNumber' in node:
        prop['columnNumber'] = node['columnNumber']
    else:
        prop['columnNumber'] = None

    if 'columnNumberEnd' in node:
        prop['columnNumberEnd'] = node['columnNumberEnd']
    else:
        prop['columnNumberEnd'] = None

    if 'id' in node:
        prop['id'] = str(node['id'])
    else:
        prop['id'] = None

    if '_label' in node:
        prop['_label'] = node['_label']
    else:
        prop['_label'] = None

    if 'callee_id' in node:
        prop['callee_id'] = node['callee_id']
    else:
        prop['callee_id'] = None

    if 'typeFullName' in node:
        prop['typeFullName'] = node['typeFullName']
    else:
        prop['typeFullName'] = None

    return prop


def complete_graph(dot_dict, id2node, callee_dict, graph_db_dir, type):
    # dot_dict 存储dot文件的字典
    # id2node 存储所有结点信息的字典
    # callee_dict 存储所有callee信息的字典
    # graph_db_dir 存储生成的pdg、ast信息的目录
    # 每个pdg生成一个igraph对象并存储在pkl文件中，对于pdg中的call结点，还会记录其callee信息，最终每个pkl的文件名为funcname_funcid
    # 每个ast文件同样如此
    try:
        for func_id in dot_dict:

            func_name = id2node[func_id]['name']
            dot_g = dot_dict[func_id]

            nodes = dot_g.get_nodes()
            if len(nodes) == 0:
                continue
            g = Graph(directed=True)
            edges = dot_g.get_edges()
            # 加入所有结点
            for node in nodes:
                id = json.loads(node.get_name())
                if type == 'pdg':
                    if id2node[id]["_label"] == "CALL" and id2node[id]["name"].find("<operator>.") == -1:
                        if id in callee_dict:
                            id2node[id]["callee_id"] = callee_dict[id]
                        else:
                            print(id+"\terror")
                    id2node[id]['IsPdgNode'] = True
                prop = generate_prop_for_node(func_id, id2node[id])
                if type == 'ast':
                    if'IsPdgNode' in id2node[id]:
                        prop['IsPdgNode'] = id2node[id]['IsPdgNode']
                    else:
                        prop['IsPdgNode'] = False

                g.add_vertex(id, **prop)

            # 加入所有边
            for edge in edges:
                start_node_id = json.loads(edge.get_source())
                end_node_id = json.loads(edge.get_destination())
                g.add_edge(start_node_id, end_node_id, **
                           (edge.obj_dict['attributes']))
            # func_id = json.loads(nodes[0].get_name())

            func_file_path = id2node[func_id]['filename']
            func_file_dir, func_file_name = os.path.split(func_file_path)
            index = func_file_dir.find('/raw')
            pkl_dir = graph_db_dir+func_file_dir[index+4:]
            pkl_dir = f"{pkl_dir}/{type}"
            if os.path.exists(pkl_dir) == False:
                os.makedirs(pkl_dir)
            pdg_file_path = pkl_dir+f"/{func_name}_{func_id}.pkl"
            # print(pdg_file_path)
            with open(pdg_file_path, "wb+")as f1:
                pickle.dump(g, f1)
        print(f"-----completing {type} successfully!-----")
    except Exception as e:
        print(f"-----completing {type} failed!-----")
        print(e)
        sys.exit(0)


if __name__ == '__main__':
    # 所有结点id以字符串形式存储，这是因为从dot文件中解析出来的id是字符串形式的
    joern_parse_dir = '/home/wanghu/new_joern/v1_1_519/joern-parse'  # 需根据自己的环境进行修改

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

    callIn_path = intermediate_dir+"/callIn.json"  # 存储callIn信息的json文件
    callIn_dict = get_all_callIn(client, raw_dir, callIn_path)

    node_list_path = intermediate_dir + "/allnodes.json"  # 存储所有结点的json文件
    id2node = get_all_nodes(client, node_list_path)

    dot_list_path = intermediate_dir+"/dot.json"  # 存储所有 pdg dot的json文件
    pdg_dict, ast_dict = get_all_dotfile(
        client, raw_dir, dot_list_path, id2node)

    callee_list_path = intermediate_dir+"/callee.json"  # 存储callee信息的json文件
    callee_dict = get_all_callee(client, callee_list_path)

    # 根据以上信息生成igraph形式的pdg、ast,并按照源代码目录结构存储
    complete_graph(pdg_dict, id2node, callee_dict, graph_db_dir, "pdg")
    complete_graph(ast_dict, id2node, callee_dict, graph_db_dir, "ast")

    # joern_parse(joern_parse_dir,raw_dir,bin_path)
