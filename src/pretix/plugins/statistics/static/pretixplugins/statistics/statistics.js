/*globals $, Morris, gettext, django*/
function gettext(msgid) {
    if (typeof django !== 'undefined' && typeof django.gettext !== 'undefined') {
        return django.gettext(msgid);
    }
    return msgid;
}
$(function () {
    $(".chart").css("height", "280px");

    var areaDefaults = {
        smooth: false,
        resize: true,
        fillOpacity: 0.15,
        behaveLikeLine: true,
        lineWidth: 2,
        pointSize: 4,
        gridTextSize: 12,
        gridTextColor: '#888',
        gridLineColor: '#f0f0f0'
    };
    var lineColors = ['#6d28d9', '#22c55e'];

    new Morris.Area($.extend({}, areaDefaults, {
        element: 'obd_chart',
        data: JSON.parse($("#obd-data").html()),
        xkey: 'date',
        ykeys: ['ordered', 'paid'],
        labels: [gettext('Placed orders'), gettext('Paid orders')],
        lineColors: lineColors
    }));
    new Morris.Area($.extend({}, areaDefaults, {
        element: 'obt_chart',
        data: JSON.parse($("#obt-data").html()),
        xkey: 'date',
        ykeys: ['ordered', 'paid'],
        labels: [gettext('Placed orders'), gettext('Paid orders')],
        lineColors: lineColors
    }));
    new Morris.Area($.extend({}, areaDefaults, {
        element: 'abd_chart',
        data: JSON.parse($("#abd-data").html()),
        xkey: 'date',
        ykeys: ['ordered', 'paid'],
        labels: [gettext('Attendees (ordered)'), gettext('Attendees (paid)')],
        lineColors: lineColors
    }));
    new Morris.Area($.extend({}, areaDefaults, {
        element: 'abt_chart',
        data: JSON.parse($("#abt-data").html()),
        xkey: 'date',
        ykeys: ['ordered', 'paid'],
        labels: [gettext('Attendees (ordered)'), gettext('Attendees (paid)')],
        lineColors: lineColors
    }));
    new Morris.Area($.extend({}, areaDefaults, {
        element: 'rev_chart',
        data: JSON.parse($("#rev-data").html()),
        xkey: 'date',
        ykeys: ['revenue'],
        labels: [gettext('Total revenue')],
        lineColors: ['#6d28d9'],
        preUnits: $.trim($("#currency").html()) + ' '
    }));
    new Morris.Bar({
        element: 'obp_chart',
        data: JSON.parse($("#obp-data").html()),
        xkey: 'item_short',
        ykeys: ['ordered', 'paid'],
        labels: [gettext('Placed orders'), gettext('Paid orders')],
        barColors: ['#6d28d9', '#22c55e'],
        gridTextSize: 12,
        gridTextColor: '#888',
        gridLineColor: '#f0f0f0',
        hoverCallback: function (index, options, content, row) {
            console.log(content);
            var $c = $("<div>" + content + "</div>");
            var $label = $c.find(".morris-hover-row-label");
            $label.text(row.item);
            var newc = $label.get(0).outerHTML;
            $c.find('.morris-hover-point').each(function (i, r) {
                if ($.trim($(r).text().split("\n")[2]) !== "0") {
                    newc += r.outerHTML;
                }
            });
            return newc;
        },
        resize: true,
        xLabelAngle: 30
    });
});
