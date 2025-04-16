from dify_plugin import Plugin, DifyPluginEnv
import logging
import sys


plugin = Plugin(DifyPluginEnv(MAX_REQUEST_TIMEOUT=120))

if __name__ == '__main__':
    
    # logger = logging.getLogger()
    # formatter = logging.Formatter('%(levelname)s:%(filename)s:%(funcName)s - %(message)s')
    # logger_handler = logging.StreamHandler(sys.stdout)
    # logger_handler.setFormatter(formatter)
    # logger.addHandler(logger_handler)
    # logger.setLevel(logging.DEBUG)

    plugin.run()
