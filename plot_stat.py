from os import walk, path
from pandas import read_csv, datetime, date_range
from matplotlib import pyplot as plt

def make_plot(source, destination):
	dateparse = lambda x: datetime.strptime(x, '%d.%m.%y %H:%M')
	data = read_csv(source, index_col=0, usecols=['Time', 'Total(BTC)'], parse_dates=True, date_parser=dateparse, encoding='utf8')
	data = data.resample('H').last()
	ylim = [data['Total(BTC)'].min(), data['Total(BTC)'].max()]
	ax = data.plot(y='Total(BTC)', kind='area', title='Equity (BTC)', legend=False, ylim=ylim, colormap='Accent')
	ax.xaxis.set_label_text('')
	ax.set_axisbelow(True)
	ax.grid(which='major', axis='y', linestyle='--')
	plt.tight_layout()
	plt.savefig(destination)

if __name__ == '__main__':
	for dirpath, dirnames, filenames in walk(path.dirname(path.realpath(__file__))):
		for filename in filenames:
			filename = path.join(dirpath, filename)
			name, ext = path.splitext(filename)
			if ext == '.csv':
				make_plot(filename, name + '.jpg')
