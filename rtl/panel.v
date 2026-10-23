module panel(input clk, input uart_rx, output uart_tx,
             input [3:0] buttons_n, input [15:0] switches,
             output reg [7:0] segments, output reg [7:0] digit_sel,
             output [3:0] leds);
    reg [7:0] powerup = 0;
    always @(posedge clk) if (!(&powerup)) powerup <= powerup + 1'b1;
    wire reset_n = &powerup;
    wire [7:0] rx_data;
    wire rx_valid;
    uart_receiver rx(clk, reset_n, uart_rx, rx_data, rx_valid);
    reg tx_start;
    reg [7:0] tx_data;
    wire tx_busy;
    uart_sender tx(clk, reset_n, tx_data, tx_start, uart_tx, tx_busy);

    reg [3:0] key_meta, key_sync, keys, previous_keys;
    reg [15:0] sw_meta, sw_sync;
    reg [16:0] debounce [0:3];
    reg [31:0] events;
    integer k;
    assign leds = keys;
    always @(posedge clk) begin
        if (!reset_n) begin
            key_meta <= 0; key_sync <= 0; keys <= 0; previous_keys <= 0;
            sw_meta <= 0; sw_sync <= 0; events <= 0;
            for (k=0;k<4;k=k+1) debounce[k] <= 0;
        end else begin
            key_meta <= ~buttons_n; key_sync <= key_meta;
            sw_meta <= switches; sw_sync <= sw_meta;
            previous_keys <= keys;
            if (|(keys & ~previous_keys)) events <= events + 1'b1;
            for (k=0;k<4;k=k+1) begin
                if (key_sync[k] == keys[k]) debounce[k] <= 0;
                else if (debounce[k] == 124999) begin
                    keys[k] <= key_sync[k]; debounce[k] <= 0;
                end else debounce[k] <= debounce[k] + 1'b1;
            end
        end
    end

    function [7:0] hexchar;
        input [3:0] value;
        begin hexchar = value < 10 ? 8'd48 + value : 8'd55 + value; end
    endfunction
    function [63:0] decimal_chars;
        input [31:0] value;
        integer j;
        begin
            for (j=0;j<8;j=j+1)
                decimal_chars[j*8 +: 8] = 8'd48 + value[j*4 +: 4];
        end
    endfunction
    function [63:0] hex_chars;
        input [31:0] value;
        integer j;
        begin
            for (j=0;j<8;j=j+1)
                hex_chars[j*8 +: 8] = hexchar(value[j*4 +: 4]);
        end
    endfunction

    reg [31:0] display_value, candidate;
    reg [1:0] command;
    reg [3:0] length;
    reg invalid, pending, sending;
    reg [21:0] rx_timeout;
    reg [223:0] frame;
    reg [5:0] remaining;
    always @(posedge clk) begin
        if (!reset_n) begin
            display_value <= 0; candidate <= 0; command <= 0; length <= 0;
            invalid <= 0; pending <= 0; sending <= 0; tx_start <= 0;
            tx_data <= 0; remaining <= 0; frame <= 0; rx_timeout <= 0;
        end else begin
            tx_start <= 0;
            if (command != 0) begin
                if (rx_timeout == 2499999) begin command <= 0; rx_timeout <= 0; end
                else rx_timeout <= rx_timeout + 1'b1;
            end
            if (pending && !sending && !tx_busy && !tx_start) begin
                frame <= {"P1 ", decimal_chars(display_value), " ", hexchar(keys), " ",
                          hexchar(sw_sync[15:12]),hexchar(sw_sync[11:8]),
                          hexchar(sw_sync[7:4]),hexchar(sw_sync[3:0])," ",hex_chars(events),8'h0a};
                remaining <= 28; sending <= 1; pending <= 0;
            end
            if (sending && !tx_busy && !tx_start) begin
                if (remaining == 0) sending <= 0;
                else begin
                    tx_data <= frame[223:216]; tx_start <= 1;
                    frame <= {frame[215:0],8'h00}; remaining <= remaining - 1'b1;
                end
            end
            if (rx_valid) begin
                rx_timeout <= 0;
                if (rx_data == "D") begin command <= 1; length <= 0; invalid <= 0; candidate <= 0; end
                else if (rx_data == "Q") begin command <= 2; length <= 0; invalid <= 0; end
                else if (rx_data == 10) begin
                    if (command == 1 && length == 8 && !invalid) begin
                        display_value <= candidate; pending <= 1;
                    end else if (command == 2 && !invalid) pending <= 1;
                    command <= 0;
                end else if (rx_data != 13) begin
                    if (command == 1 && length < 8 && rx_data >= "0" && rx_data <= "9") begin
                        candidate <= {candidate[27:0],rx_data[3:0]}; length <= length + 1'b1;
                    end else invalid <= 1;
                end
            end
        end
    end

    function [7:0] glyph;
        input [3:0] number;
        begin
            case (number)
                0:glyph=8'hc0; 1:glyph=8'hf9; 2:glyph=8'ha4; 3:glyph=8'hb0;
                4:glyph=8'h99; 5:glyph=8'h92; 6:glyph=8'h82; 7:glyph=8'hf8;
                8:glyph=8'h80; 9:glyph=8'h90; default:glyph=8'hff;
            endcase
        end
    endfunction
    reg [11:0] scan_count;
    reg [2:0] position;
    always @(posedge clk) begin
        if (!reset_n) begin
            scan_count <= 0; position <= 0; segments <= 8'hff; digit_sel <= 0;
        end else begin
            if (scan_count == 3124) begin scan_count <= 0; position <= position + 1'b1; end
            else scan_count <= scan_count + 1'b1;
            if (scan_count == 0) digit_sel <= 0;
            if (scan_count == 1) segments <= glyph((display_value >> ((7-position)*4)) & 4'hf);
            // Board selects count from right to left within each four-digit group.
            if (scan_count == 2) digit_sel <= 8'b1 << {position[2], ~position[1:0]};
        end
    end
endmodule

module uart_receiver(input clk,input reset_n,input rx,output reg [7:0] data,output reg valid);
    reg meta, sync;
    reg [1:0] state;
    reg [15:0] count;
    reg [2:0] bit_index;
    reg [7:0] buffer;
    always @(posedge clk) begin
        if (!reset_n) begin meta<=1;sync<=1;state<=0;count<=0;bit_index<=0;buffer<=0;data<=0;valid<=0;end
        else begin
            meta<=rx;sync<=meta;valid<=0;
            case(state)
                0: if (!sync) begin count<=108;state<=1;end
                1: if(count!=0) count<=count-1'b1;
                   else if(!sync) begin count<=216;bit_index<=0;state<=2;end
                   else state<=0;
                2: if(count!=0) count<=count-1'b1;
                   else begin buffer[bit_index]<=sync;count<=216;
                       if(bit_index==7) state<=3;else bit_index<=bit_index+1'b1;end
                3: if(count!=0) count<=count-1'b1;
                   else begin if(sync) begin data<=buffer;valid<=1;end state<=0;end
            endcase
        end
    end
endmodule

module uart_sender(input clk,input reset_n,input [7:0] data,input start,output reg tx,output reg busy);
    reg [9:0] shift;
    reg [15:0] count;
    reg [3:0] bits_left;
    always @(posedge clk) begin
        if(!reset_n) begin tx<=1;busy<=0;shift<=10'h3ff;count<=0;bits_left<=0;end
        else if(!busy) begin
            tx<=1;
            if(start) begin shift<={1'b1,data,1'b0};tx<=0;count<=216;bits_left<=10;busy<=1;end
        end else if(count!=0) count<=count-1'b1;
        else begin
            count<=216;shift<={1'b1,shift[9:1]};bits_left<=bits_left-1'b1;
            if(bits_left==1) begin busy<=0;tx<=1;end else tx<=shift[1];
        end
    end
endmodule
