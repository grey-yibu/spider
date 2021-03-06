# -*- coding: utf-8 -*-
'''
抓取贝壳网的信息
'''


from lxml import etree


import tools
import log
import codecs
import re
import global_obj
import csv

import thread_tool


from spider import get_url,new_session,url_encode,js2py_val,is_not_ok

g_session = None

def trim_str(s):
    return s.replace("\n", "").replace(" ", "")

def __get_community_info_desc(cityName, keyword, filter_word = None):
    return "获取小区信息:<%s-%s>完成"%(cityName,keyword)

#获取小区信息
@tools.check_use_time(5, tools.global_log, __get_community_info_desc)
def get_community_info(cityName, keyword, filter_word = None):
    '''
    cityName: 城市
    keyword: 小区名
    filter_word 过滤关键字， 对region进行匹配
    @return
        返回小区列表
    '''
    global g_session

    data = {
        "cityName":cityName,
        "channel":"xiaoqu",
        "keyword": keyword,
        "query": keyword,
    }

    url = url_encode("https://ajax.api.ke.com/sug/headerSearch", data)
    result,_ = get_url(url, session = g_session)
    result_list = {}
    if is_not_ok(result) :
        log.Error("get_community_info url false", cityName, keyword, result.status_code)
        return
    result_data = js2py_val(result.content)
    if result_data["errno"] != 0:
        log.Error("get_community_info not ok", cityName, keyword)
        return result_list
    if len(result_data["data"]) == 0:
        log.Waring("get_community_info data is nil")
        return result_list
    for data in result_data["data"]["result"]:
        if filter_word and not filter_word in data["region"]:
            log.Info("get_community_info ingore by filter_word", cityName, keyword, data)
            continue
        new_data = {
            "city":cityName,
            "name" : data["text"],
            "id" : data["id"],
            "region":data["region"],
            "house_url_list" : [],
            "house_data":{},
        }
        new_data["house_url_list"] = get_house_list(data["id"])
        result_list[new_data["id"]] = new_data
    

    return result_list

__pHouseID = re.compile(".*?(\d+)\.html")




#通过小区ID找到房子
@tools.check_use_time(2, tools.global_log, "小区二手房数据用时")
def get_house_list(cid):
    url = "https://gz.ke.com/ershoufang/c%s/"%(cid)
    global g_session
    result,_ = get_url(url, session = g_session)
    if result.status_code != 200 :
        log.Waring("get_house_list url false", cid)
        return False
    
    #获取房子列表
    tree = etree.HTML(result.text)
    url_ls = tree.xpath('//div[@class="leftContent"]//ul[@class="sellListContent"]//li[@class="clear"]/a/@href')

    return url_ls


@tools.check_use_time(1, tools.global_log, "爬取房子信息超时")
def get_house_info(url, house_data):
    def get_total(data, htree):
        ls  = htree.xpath('.//div[@class="overview"]//span[@class="total"]/text()')
        if len(ls) == 0 or not tools.is_float(ls[0]):
            log.Waring("get_house_list -> get_total false")
            return
        data["价格"] = tools.tofloat(ls[0])
    
    def get_info(data, htree):
        #基本属性

        def get_info2(key):
            parttern = './div[@data-component="baseinfo"]//div[@class="introContent"]//div[@class="%s"]//ul//li'%(key)
            ls = htree.xpath(parttern)
            if len(ls) == 0:
                log.Waring("get_house_list -> get_info -> get_info2 false", key)
                return
            d = {}
            for li in ls:
                ls1 = li.xpath('./span/text()')
                if len(ls1) > 1 and trim_str(ls1[0]) == "抵押信息": #特殊处理该处信息
                    ls2 = ls1[1:]
                else:
                    ls2 = li.xpath('./text()')
                if len(ls1) == 0 or len(ls2) == 0:
                    log.Waring("get_house_list -> get_info base false", ls1, ls2)
                    continue
                k = trim_str(ls1[0])
                v = trim_str(ls2[0])
                data[k] = v
            #data[key] = d

        get_info2("base")
        get_info2("transaction")

    r = re.match(__pHouseID, url)
    if not r:
        log.Error("get_house_list no hid", url)
        return None
    house_info = {
        "id": r.groups()[0],
    }
    result,_ = get_url(url, session = g_session)
    if result.status_code != 200 :
        log.Waring("request house url false", url)
        return None
    htree = etree.HTML(result.text)
    
    ls = htree.xpath('//div[@class="sellDetailPage"]//div[@data-component="overviewIntro"]')
    if len(ls) > 0:
        get_total(house_info, ls[0])
    ls = htree.xpath('//div[@class="sellDetailPage"]//div[@class="m-content"]//div[@class="box-l"]')
    if len(ls) > 0:
        get_info(house_info, ls[0])
    house_data[house_info["id"]] = house_info





def get_all_community(cityName):
    return []




###################### 对外接口 ######################

DATA_PATH = "./tmp/"



def save_community_csv(data):
    #print("data", data)
    file = DATA_PATH + "%s_%s.csv"%(data["name"], data["region"])
    f = open(file,'w', encoding="utf-8", newline='')
    writer = csv.writer(f)
    format_list = None
    for hid, house in data["house_data"].items():
        if not format_list:
            format_list = house.keys()
            writer.writerow(format_list)
        row = [ house.get(s,"") for s in format_list]
        writer.writerow(row)
    
    f.close()







@tools.check_use_time(0, tools.global_log, "所有小区新爬取完成，用时")
def start_community():
    '''
    使用多线程爬取小区
    '''
    beike_conf = global_obj.get("config")["beike"]
    task_list = []
    for data in beike_conf["spider_list"]:
        cityName = data["city"]
        if "all" in data:
            community_list = get_all_community(cityName)
        else:
            community_list = data["community"]
        filterWord = None
        if "filter" in data:
            filterWord = data["filter"]
        for cName in community_list:
            task_list.append((cityName, cName, filterWord,))
    
    task2_list = []
    data_list = []
    def _get_community_info(threadobj, cityName, cName, filterWord):
        result_list = get_community_info(cityName, cName, filterWord)
        data_list.extend(result_list.values())
        for cid, data in result_list.items():
            for url in data["house_url_list"]:
                task2_list.append((url, data["house_data"]))
            del data["house_url_list"]


    thread_tool.start_thread(_get_community_info, task_list, 5)
    log.Info("爬取小区信息完毕")
    def _get_house_info(tobj, url, house_data):
        get_house_info(url, house_data)
    
    thread_tool.start_thread(_get_house_info, task2_list, 10)
    for community in data_list:
        save_community_csv(community)
        log.Info("存储<%s-%s>小区完毕"%(community["city"], community["name"]))


def init():
    #需要先获得cookies后再执行其他请求
    global g_session
    g_session = new_session()
    url = "https://gz.ke.com/?utm_source=baidu&utm_medium=pinzhuan&utm_term=biaoti&utm_content=biaotimiaoshu&utm_campaign=wyguangzhou"
    result,g_session = get_url(url, session = g_session)


################ 测试 ###########################

@tools.check_use_time(1, tools.global_log)
def test():
    #result = get_community_info("广州", "新天美地")
    
    file = "./tmp/新天美地花园_ 荔城富鹏_增城.csv"
    writer = csv.writer(open(file,'w', encoding="utf-8", newline=''))
    writer.writerow(("a","b","c"))
    writer.writerow(("a","b","c"))
    writer.writerow(("sssa","ddb","cff"))















