import logging
from typing import Optional


def get_logger(name: Optional[str] = None, level: int = logging.INFO) -> logging.Logger:
    """
    シンプルなロガー生成関数。

    Parameters
    ----------
    name : str | None
        ロガー名。None の場合は root ロガーを返す。
    level : int
        ログレベル (logging.INFO など)。

    Returns
    -------
    logging.Logger
        使い回し可能なロガーインスタンス
    """
    logger = logging.getLogger(name)

    # ハンドラがまだ無ければ最低限の設定を追加
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(level)

    return logger
