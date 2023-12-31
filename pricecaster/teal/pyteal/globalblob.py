# NOTE: This is an almost exact copy of the local_blob code from Wormhole

from typing import Tuple

from pyteal import *

_max_keys = 63 
_page_size = 128 - 1  # need 1 byte for key
_max_bytes = _max_keys * _page_size
_max_bits = _max_bytes * 8

max_keys = Int(_max_keys)
page_size = Int(_page_size)
max_bytes = Int(_max_bytes)


def _key_and_offset(idx: Int) -> Tuple[Int, Int]:
    return idx / page_size, idx % page_size


@Subroutine(TealType.bytes)
def intkey(i: Expr) -> Expr:
    return Extract(Itob(i), Int(7), Int(1))


# TODO: Add Keyspace range?
class GlobalBlob:
    """
    GlobalBlob is a class holding static methods to work with the global storage as a binary large object

    The `zero` method must be called on an account on opt in and the schema of the local storage should be 16 bytes
    """

    @staticmethod
    @Subroutine(TealType.none)
    def zero() -> Expr:
        """
        initializes global state to all zero bytes

        This allows us to be lazy later and _assume_ all the strings are the same size

        """
        i = ScratchVar()
        init = i.store(Int(0))
        cond = i.load() < max_keys
        iter = i.store(i.load() + Int(1))
        return For(init, cond, iter).Do(
            App.globalPut(intkey(i.load()), BytesZero(page_size))
        )

    @staticmethod
    @Subroutine(TealType.uint64)
    def get_byte(idx: Expr):
        """
        Get a single byte from global storage by index
        """
        key, offset = _key_and_offset(idx)
        return GetByte(App.globalGet(intkey(key)), offset)

    @staticmethod
    @Subroutine(TealType.none)
    def set_byte(idx: Expr, byte: Expr):
        """
        Set a single byte from global storage by index
        """
        key, offset = _key_and_offset(idx)
        return App.globalPut(
            intkey(key), SetByte(App.globalGet(intkey(key)), offset, byte)
        )

    @staticmethod
    @Subroutine(TealType.bytes)
    def read(
        bstart: Expr, bend: Expr
    ) -> Expr:
        """
        read bytes between bstart and bend from global storage by index
        """

        start_key, start_offset = _key_and_offset(bstart)
        stop_key, stop_offset = _key_and_offset(bend)

        key = ScratchVar()
        buff = ScratchVar()

        start = ScratchVar()
        stop = ScratchVar()

        init = key.store(start_key)
        cond = key.load() <= stop_key
        incr = key.store(key.load() + Int(1))

        return Seq(
            buff.store(Bytes("")),
            For(init, cond, incr).Do(
                Seq(
                    start.store(If(key.load() == start_key, start_offset, Int(0))),
                    stop.store(If(key.load() == stop_key, stop_offset, page_size)),
                    buff.store(
                        Concat(
                            buff.load(),
                            Substring(
                                App.globalGet(intkey(key.load())),
                                start.load(),
                                stop.load(),
                            ),
                        )
                    ),
                )
            ),
            buff.load(),
        )

    @staticmethod
    @Subroutine(TealType.none)
    def write(
        bstart: Expr, buff: Expr
    ) -> Expr:
        """
        write bytes between bstart and len(buff) to global storage
        """

        start_key, start_offset = _key_and_offset(bstart)
        stop_key, stop_offset = _key_and_offset(bstart + Len(buff))

        key = ScratchVar()
        start = ScratchVar()
        stop = ScratchVar()
        written = ScratchVar()

        init = key.store(start_key)
        cond = key.load() <= stop_key
        incr = key.store(key.load() + Int(1))

        delta = ScratchVar()

        return Seq(
            written.store(Int(0)),
            For(init, cond, incr).Do(
                Seq(
                    start.store(If(key.load() == start_key, start_offset, Int(0))),
                    stop.store(If(key.load() == stop_key, stop_offset, page_size)),
                    App.globalPut(
                        intkey(key.load()),
                        If(
                            Or(stop.load() != page_size, start.load() != Int(0))
                        )  # Its a partial write
                        .Then(
                            Seq(
                                delta.store(stop.load() - start.load()),
                                Concat(
                                    Substring(
                                        App.globalGet(intkey(key.load())),
                                        Int(0),
                                        start.load(),
                                    ),
                                    Extract(buff, written.load(), delta.load()),
                                    Substring(
                                        App.globalGet(intkey(key.load())),
                                        stop.load(),
                                        page_size,
                                    ),
                                ),
                            )
                        )
                        .Else(
                            Seq(
                                delta.store(page_size),
                                Extract(buff, written.load(), page_size),
                            )
                        ),
                    ),
                    written.store(written.load() + delta.load()),
                )
            )
        )
