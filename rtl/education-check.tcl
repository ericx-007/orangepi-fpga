# Compile check only. Hardware programming requires device compatibility evidence.
set_device -name GW5AST-138B GW5AST-LV138PG484AC1/I0
add_file panel.v
add_file panel.cst
add_file panel.sdc
set_option -top_module panel
set_option -output_base_name panel
run all
