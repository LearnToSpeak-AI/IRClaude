from myorch.services.dev_server_manager import RingBuffer


def test_ring_buffer_appends_lines():
    rb = RingBuffer(capacity=3)
    rb.append("a")
    rb.append("b")
    assert rb.tail() == ["a", "b"]


def test_ring_buffer_drops_oldest():
    rb = RingBuffer(capacity=3)
    for ch in "abcde":
        rb.append(ch)
    assert rb.tail() == ["c", "d", "e"]


def test_ring_buffer_clear():
    rb = RingBuffer(capacity=3)
    rb.append("x")
    rb.clear()
    assert rb.tail() == []
