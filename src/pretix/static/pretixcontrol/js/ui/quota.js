/*globals $, Morris, gettext*/
$(function () {
    if (!$("#quota-stats").length) {
        return;
    }

    $(".chart").css("height", "250px");
    new Morris.Donut({
        element: 'quota_chart',
        data: JSON.parse($("#quota-chart-data").html()),
        resize: true,
        colors: [
            '#3b82f6', // paid
            '#60a5fa', // pending
            '#ef4444', // vouchers
            '#f59e0b', // carts
            '#22c55e'  // available
        ],
        formatter: function (x) { return x; }
    });
});

$(function () {
    if (!$("input[name=itemvars]").length) {
        return;
    }
    var autofill = ($("#id_name").val() === "");

    $("#id_name").on("change keyup keydown keypress", function () {
        autofill = false;
    })

    function do_autofill() {
        if (autofill) {
            var names = [];
            $("input[name=itemvars]:checked").each(function () {
                names.push($.trim($(this).closest("label").text()))
            });
            $("#id_name").val(names.join(', '));
        }
    }
    $("input[name=itemvars]").change(do_autofill);
    do_autofill();
});
