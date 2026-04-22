python3 -m noa.noa $1 -v \
    --bit examples/daq/design_1_wrapper.bit \
    --hwh examples/daq/design_1.hwh \
    --daq-output - \
    --daq-channels "1:fixdt(1,32,29)" "3:fixdt(1,32,29)" "5:fixdt(1,32,29)" \
    --daq-window 100 \
    --daq-trigger RisingEdge \
    --daq-trigger-ch 0 \
    --daq-trigger-threshold 0 \
    --daq-trigger-hysteresis 10 