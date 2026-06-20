import gzip
import logging
import logging.handlers
import os
import shutil
from pathlib import Path

project_root = Path(__file__).parent.parent
LOG_DIR = project_root / 'data' / 'log'


class CompressedRotatingFileHandler(logging.handlers.RotatingFileHandler):
    """自訂的 RotatingFileHandler，支援自動壓縮舊的 log 檔案"""

    def doRollover(self):
        """
        執行日誌輪替，並壓縮舊的日誌檔案
        """
        if self.stream:
            self.stream.close()
            self.stream = None  # type: ignore[assignment]

        # 如果存在備份檔案，先將它們重新命名
        if self.backupCount > 0:
            for i in range(self.backupCount - 1, 0, -1):
                sfn = Path(self.rotation_filename(f'{self.baseFilename}.{i}'))
                dfn = Path(self.rotation_filename(f'{self.baseFilename}.{i + 1}'))

                # 檢查是否有壓縮檔
                sfn_gz = sfn.with_suffix(sfn.suffix + '.gz')
                dfn_gz = dfn.with_suffix(dfn.suffix + '.gz')

                if sfn_gz.exists():
                    if dfn_gz.exists():
                        dfn_gz.unlink()
                    sfn_gz.rename(dfn_gz)
                elif sfn.exists():
                    if dfn_gz.exists():
                        dfn_gz.unlink()
                    # 壓縮並移動檔案
                    self._compress_file(sfn, dfn_gz)
                    sfn.unlink()

            # 處理第一個備份檔案
            dfn = Path(self.rotation_filename(f'{self.baseFilename}.1'))
            base_file = Path(self.baseFilename)
            
            if base_file.exists():
                # 壓縮當前檔案並儲存為 .1.gz
                dfn_gz = dfn.with_suffix(dfn.suffix + '.gz')
                self._compress_file(base_file, dfn_gz)
                base_file.unlink()

        # 開啟新的日誌檔案
        if not self.delay:
            self.stream = self._open()

    def _compress_file(self, source_path: Path, dest_path: Path):
        """
        使用 gzip 壓縮檔案

        Args:
            source_path: 原始檔案路徑 (Path 物件)
            dest_path: 壓縮後檔案路徑 (Path 物件，應以 .gz 結尾)
        """
        try:
            with source_path.open('rb') as f_in:
                with gzip.open(dest_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
        except Exception as e:
            # 如果壓縮失敗，記錄錯誤但不影響日誌系統運作
            print(f'壓縮日誌檔案失敗: {source_path} -> {dest_path}, 錯誤: {e}')


class CustomFormatter(logging.Formatter):
    LEVEL_COLORS = [
        (logging.DEBUG, '\x1b[40;1m'),
        (logging.INFO, '\x1b[34;1m'),
        (logging.WARNING, '\x1b[33;1m'),
        (logging.ERROR, '\x1b[31m'),
        (logging.CRITICAL, '\x1b[41m'),
    ]
    FORMATS = {
        level: logging.Formatter(
            f'\x1b[30;1m%(asctime)s\x1b[0m {color}%(levelname)-8s\x1b[0m \x1b[35m%(name)s\x1b[0m -> %(message)s',
            '%Y-%m-%d %H:%M:%S',
        )
        for level, color in LEVEL_COLORS
    }

    def format(self, record):
        formatter = self.FORMATS.get(record.levelno)
        if formatter is None:
            formatter = self.FORMATS[logging.DEBUG]

        # 覆寫追蹤資訊，總是以紅色印出
        if record.exc_info:
            text = formatter.formatException(record.exc_info)
            record.exc_text = f'\x1b[31m{text}\x1b[0m'

        output = formatter.format(record)
        # 移除快取層
        record.exc_text = None
        return output


def setup_logger(module_name: str) -> logging.Logger:
    # 建立日誌記錄器
    library, _, _ = module_name.partition('.py')
    logger = logging.getLogger(library)

    # 避免重複新增處理器
    if not logger.hasHandlers():
        logger.setLevel(logging.INFO)
        level = logging.INFO

        # 建立控制台處理器
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(CustomFormatter())
        logger.addHandler(console_handler)

        if os.getenv('LOGGING') == 'True':  # 檢查是否啟用檔案日誌記錄
            log_path = LOG_DIR / 'DCbot.py.log'

            # 確保日誌目錄存在
            LOG_DIR.mkdir(parents=True, exist_ok=True)

            # 建立檔案處理器
            log_handler = CompressedRotatingFileHandler(
                filename=log_path,
                encoding='utf-8',
                maxBytes=8 * 1024 * 1024,  # 8 MiB
                backupCount=5,  # 輪替 5 個檔案
            )
            log_handler.setFormatter(CustomFormatter())
            log_handler.setLevel(level)
            logger.addHandler(log_handler)

        # 防止日誌記錄器將訊息傳播至根日誌記錄器
        logger.propagate = False

    return logger


main_logger = setup_logger('main')
cogs_logger = setup_logger('cogs')
db_logger = setup_logger('db')
